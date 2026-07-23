from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Callable

from kubeops_core.actions import ActionCatalog
from kubeops_core.models.operation import (
    ActionReceipt,
    ApprovalRecord,
    ExecutionCheckpoint,
    OperationEvent,
    OperationRun,
)
from kubeops_core.models.planning import ActionInstance, ExecutionPolicy, RecoveryPlan
from kubeops_core.models.relationship import Relationship
from kubeops_core.models.verification import RecoveryCertificate, VerificationCondition
from kubeops_core.policy import PolicyContext, PolicyEngine
from kubeops_core.util import utc_now_iso
from kubeops_core.verification import VerificationEngine

from .executors import ExecutionContext, ExecutorRegistry
from .store import FileOperationStore


@dataclass
class RuntimeContext:
    policy_context: PolicyContext
    execution_context: ExecutionContext
    world_provider: Callable[[], dict[str, dict]]
    relationships_provider: Callable[[], list[Relationship]] = lambda: []


class OperationRuntime:
    def __init__(
        self,
        actions: ActionCatalog,
        executors: ExecutorRegistry,
        store: FileOperationStore,
        policy_engine: PolicyEngine | None = None,
        verification_engine: VerificationEngine | None = None,
    ) -> None:
        self.actions = actions
        self.executors = executors
        self.store = store
        self.policy = policy_engine or PolicyEngine()
        self.verification = verification_engine or VerificationEngine()

    def create(
        self,
        environment_id: str,
        plan: RecoveryPlan,
        *,
        mode: str = "dry_run",
        approvals: list[ApprovalRecord] | None = None,
    ) -> OperationRun:
        for action in plan.actions:
            self.actions.validate_instance(action)
        now = utc_now_iso()
        operation_id = f"operation:{environment_id}:{plan.plan_id.split(':')[-1]}"
        operation = OperationRun(
            operation_id=operation_id,
            environment_id=environment_id,
            operation_type=plan.operation_type,
            objective_id=plan.objective_id,
            status="created",
            mode=mode,  # type: ignore[arg-type]
            plan=plan.model_copy(update={"mode": mode}),
            approvals=approvals or [],
            created_at_iso=now,
            updated_at_iso=now,
            events=[self._event(operation_id, 0, "operation.created", "Operation created")],
        )
        self.store.save(operation)
        return operation

    def authorize(self, operation: OperationRun, policy: ExecutionPolicy, context: RuntimeContext) -> OperationRun:
        effective_mode = "dry_run" if operation.mode == "dry_run" else context.execution_context.mode
        policy_context = replace(context.policy_context, execution_mode=effective_mode)
        decisions = [
            self.policy.evaluate(
                action,
                self.actions.validate_instance(action),
                policy,
                policy_context,
                operation.approvals,
            )
            for action in operation.plan.actions
        ]
        denied = [item for item in decisions if item.outcome == "deny"]
        pending = [item for item in decisions if item.outcome == "approval_required"]
        if denied:
            status = "blocked"
            title = f"Authorization denied for {len(denied)} action(s)"
        elif pending:
            status = "awaiting_approval"
            title = f"Awaiting approval for {len(pending)} action(s)"
        else:
            status = "authorized"
            title = "All planned actions authorized"
        decision_by_action = {item.action_id: item for item in decisions}
        authorized_actions = []
        for action in operation.plan.actions:
            decision = decision_by_action[action.action_id]
            action_status = {
                "allow": "authorized",
                "approval_required": "approval_required",
                "deny": "blocked",
            }[decision.outcome]
            authorized_actions.append(action.model_copy(update={"status": action_status}))
        operation = operation.model_copy(
            update={
                "status": status,
                "plan": operation.plan.model_copy(update={"actions": authorized_actions}),
                "policy_decisions": decisions,
                "updated_at_iso": utc_now_iso(),
                "events": [*operation.events, self._event(operation.operation_id, len(operation.events), "operation.authorization_evaluated", title, details={"decision_count": len(decisions)})],
            }
        )
        self.store.save(operation)
        return operation

    def add_approval(self, operation: OperationRun, approval: ApprovalRecord) -> OperationRun:
        if approval.operation_id != operation.operation_id:
            raise ValueError("approval belongs to a different operation")
        operation = operation.model_copy(
            update={
                "approvals": [*operation.approvals, approval],
                "updated_at_iso": utc_now_iso(),
                "events": [*operation.events, self._event(operation.operation_id, len(operation.events), "approval.recorded", f"Approval {approval.decision} by {approval.approver_id}", action_id=approval.action_id)],
            }
        )
        self.store.save(operation)
        return operation

    def run(
        self,
        operation: OperationRun,
        policy: ExecutionPolicy,
        context: RuntimeContext,
        verification_conditions: list[VerificationCondition] | None = None,
        *,
        rollback_on_failure: bool = True,
    ) -> OperationRun:
        operation = self.authorize(operation, policy, context)
        if operation.status not in {"authorized"}:
            return operation
        now = utc_now_iso()
        operation = operation.model_copy(
            update={
                "status": "running",
                "started_at_iso": operation.started_at_iso or now,
                "updated_at_iso": now,
                "events": [*operation.events, self._event(operation.operation_id, len(operation.events), "operation.started", "Execution started")],
            }
        )
        self.store.save(operation)

        completed_ids = {receipt.action_id for receipt in operation.action_receipts if receipt.status in {"completed", "already_satisfied", "skipped"}}
        successful_keys = {receipt.idempotency_key for receipt in operation.action_receipts if receipt.status in {"completed", "already_satisfied"} and receipt.idempotency_key}
        pending = {action.action_id: action for action in operation.plan.actions if action.action_id not in completed_ids}
        failed = False
        failure_behavior = "rollback" if rollback_on_failure else "stop"

        while pending and not failed:
            ready = [
                action for action in pending.values()
                if set(action.depends_on_action_ids).issubset(completed_ids)
            ]
            if not ready:
                operation = self._fail(operation, "no executable actions remain; dependency graph is blocked")
                failed = True
                break
            # Release 0.4 executes sequentially even if policy allows more; concurrency is a later hardening concern.
            action = sorted(ready, key=lambda item: item.action_id)[0]
            decision = next(item for item in operation.policy_decisions if item.action_id == action.action_id)
            operation = self._set_action_status(operation, action.action_id, "running", current=True)
            if decision.requires_checkpoint:
                operation = self._checkpoint(operation, context.world_provider())
            if action.idempotency_key and action.idempotency_key in successful_keys:
                receipt = self._already_satisfied(operation, action)
            else:
                receipt = self._execute_action(operation, action, context)
            operation = self._append_receipt(operation, receipt)
            pending.pop(action.action_id)
            if receipt.status in {"completed", "already_satisfied", "skipped"}:
                completed_ids.add(action.action_id)
                if receipt.idempotency_key:
                    successful_keys.add(receipt.idempotency_key)
            elif action.optional:
                completed_ids.add(action.action_id)
            else:
                failure_behavior = str(action.metadata.get("on_failure", failure_behavior))
                if failure_behavior == "continue":
                    completed_ids.add(action.action_id)
                    operation = operation.model_copy(
                        update={
                            "events": [
                                *operation.events,
                                self._event(
                                    operation.operation_id,
                                    len(operation.events),
                                    "action.failure_tolerated",
                                    f"Continuing after failed action {action.action_id}",
                                    action_id=action.action_id,
                                ),
                            ],
                            "updated_at_iso": utc_now_iso(),
                        }
                    )
                    self.store.save(operation)
                    continue
                if failure_behavior == "pause":
                    operation = operation.model_copy(
                        update={
                            "status": "paused",
                            "pause_reason": f"action {action.action_id} failed",
                            "failure_reason": f"action {action.action_id} failed",
                            "updated_at_iso": utc_now_iso(),
                            "events": [
                                *operation.events,
                                self._event(
                                    operation.operation_id,
                                    len(operation.events),
                                    "operation.paused",
                                    f"Paused after failed action {action.action_id}",
                                    action_id=action.action_id,
                                ),
                            ],
                        }
                    )
                    self.store.save(operation)
                    return operation
                failed = True
                operation = self._fail(operation, f"action {action.action_id} failed")

        if failed:
            if rollback_on_failure and failure_behavior == "rollback":
                operation = self.rollback(operation, context)
            self.store.save(operation)
            return operation

        operation = operation.model_copy(
            update={
                "status": "verifying",
                "updated_at_iso": utc_now_iso(),
                "events": [*operation.events, self._event(operation.operation_id, len(operation.events), "verification.started", "Post-action verification started")],
            }
        )
        conditions = verification_conditions if verification_conditions is not None else operation.plan.verification_conditions
        results = self.verification.evaluate(
            conditions,
            context.world_provider(),
            context.relationships_provider(),
            at_seconds=0,
        ) if conditions else []
        dry_run = operation.mode == "dry_run"
        simulated = context.execution_context.mode == "simulation"
        success = True if dry_run and not conditions else self.verification.successful(conditions, results)
        protected = self.verification.protected_violation(conditions, results)
        if protected:
            success = False
        certificate_status = "recovered" if success else "recovery_failed"
        if dry_run or simulated:
            certificate_status = "partially_recovered"
        certificate = RecoveryCertificate(
            certificate_id=f"recovery:{operation.operation_id}:{len(operation.events)}",
            operation_id=operation.operation_id,
            incident_id=operation.plan.incident_id,
            plan_id=operation.plan.plan_id,
            status=certificate_status,  # type: ignore[arg-type]
            restored_invariant_ids=[item.condition_id for item in results if str(item.status) == "healthy"],
            unresolved_invariant_ids=[item.condition_id for item in results if str(item.status) != "healthy"],
            action_receipt_ids=[item.receipt_id for item in operation.action_receipts],
            verification_result_ids=[item.result_id for item in results],
            residual_risks=(["dry run did not mutate the environment"] if dry_run else []) + (["simulation did not verify the live environment"] if simulated else []) + (["verification failed"] if not success else []),
            metadata={"dry_run": dry_run, "simulated": simulated, "protected_violation": protected},
        )
        final_status = "completed" if success or dry_run else "failed"
        operation = operation.model_copy(
            update={
                "status": final_status,
                "verification_results": results,
                "recovery_certificate": certificate,
                "completed_at_iso": utc_now_iso(),
                "updated_at_iso": utc_now_iso(),
                "events": [*operation.events, self._event(operation.operation_id, len(operation.events), "operation.sealed", f"Operation sealed as {certificate.status}")],
            }
        )
        self.store.save(operation)
        return operation

    def cancel(self, operation: OperationRun, reason: str) -> OperationRun:
        if operation.status in {"completed", "cancelled"}:
            raise ValueError(f"operation cannot be cancelled from {operation.status}")
        operation = operation.model_copy(
            update={
                "status": "cancelled",
                "pause_reason": None,
                "failure_reason": reason,
                "completed_at_iso": utc_now_iso(),
                "updated_at_iso": utc_now_iso(),
                "current_action_ids": [],
                "events": [
                    *operation.events,
                    self._event(
                        operation.operation_id,
                        len(operation.events),
                        "operation.cancelled",
                        reason,
                    ),
                ],
            }
        )
        self.store.save(operation)
        return operation

    def pause(self, operation: OperationRun, reason: str) -> OperationRun:
        if operation.status not in {"running", "authorized", "awaiting_approval"}:
            raise ValueError(f"operation cannot be paused from {operation.status}")
        operation = operation.model_copy(update={"status": "paused", "pause_reason": reason, "updated_at_iso": utc_now_iso(), "events": [*operation.events, self._event(operation.operation_id, len(operation.events), "operation.paused", reason)]})
        self.store.save(operation)
        return operation

    def resume(self, operation_id: str, policy: ExecutionPolicy, context: RuntimeContext, verification_conditions: list[VerificationCondition] | None = None) -> OperationRun:
        operation = self.store.load(operation_id)
        if operation.status not in {"paused", "failed", "awaiting_approval", "authorized", "running"}:
            raise ValueError(f"operation cannot resume from {operation.status}")
        operation = operation.model_copy(update={"status": "created", "pause_reason": None, "failure_reason": None, "updated_at_iso": utc_now_iso(), "events": [*operation.events, self._event(operation.operation_id, len(operation.events), "operation.resumed", "Operation resumed from durable journal")]})
        self.store.save(operation)
        return self.run(operation, policy, context, verification_conditions)

    def rollback(self, operation: OperationRun, context: RuntimeContext) -> OperationRun:
        operation = operation.model_copy(update={"status": "rolling_back", "updated_at_iso": utc_now_iso(), "events": [*operation.events, self._event(operation.operation_id, len(operation.events), "rollback.started", "Rollback started")]})
        receipts = list(operation.action_receipts)
        completed = [item for item in receipts if item.status == "completed"]
        for receipt in reversed(completed):
            original = next(action for action in operation.plan.actions if action.action_id == receipt.action_id)
            definition = self.actions.get(original.action_type_id)
            if not definition.rollback_action_type_id:
                continue
            rollback_definition = self.actions.get(definition.rollback_action_type_id)
            rollback_action = ActionInstance(
                action_id=f"rollback:{original.action_id}",
                action_type_id=rollback_definition.action_type_id,
                title=f"Rollback {original.title or original.action_type_id}",
                target_ids=original.target_ids,
                parameters=original.parameters,
                risk=rollback_definition.default_risk,
                status="authorized",
                idempotency_key=f"rollback:{original.idempotency_key}" if original.idempotency_key else None,
                metadata={"rollback_of": original.action_id},
            )
            rollback_receipt = self._execute_action(operation, rollback_action, context)
            rollback_receipt = rollback_receipt.model_copy(update={"status": "rolled_back" if rollback_receipt.status == "completed" else "failed"})
            operation = self._append_receipt(operation, rollback_receipt)
        certificate = RecoveryCertificate(
            certificate_id=f"rollback:{operation.operation_id}", operation_id=operation.operation_id,
            incident_id=operation.plan.incident_id, plan_id=operation.plan.plan_id,
            status="rollback_completed", action_receipt_ids=[item.receipt_id for item in operation.action_receipts],
            residual_risks=["original target invariants were not restored"],
        )
        operation = operation.model_copy(update={"status": "failed", "recovery_certificate": certificate, "completed_at_iso": utc_now_iso(), "updated_at_iso": utc_now_iso(), "events": [*operation.events, self._event(operation.operation_id, len(operation.events), "rollback.completed", "Rollback completed")]})
        self.store.save(operation)
        return operation

    def _execute_action(self, operation: OperationRun, action: ActionInstance, context: RuntimeContext) -> ActionReceipt:
        definition = self.actions.validate_instance(action)
        effective_mode = "dry_run" if operation.mode == "dry_run" else context.execution_context.mode
        if effective_mode != "dry_run" and effective_mode not in definition.supported_modes:
            raise PermissionError(
                f"action {action.action_id} does not support execution mode {effective_mode!r}"
            )
        executor = self.executors.get("dry_run" if operation.mode == "dry_run" else ("simulation" if context.execution_context.mode == "simulation" else definition.executor_id))
        last: ActionReceipt | None = None
        for attempt in range(1, definition.max_attempts + 1):
            last = executor.execute(action, definition, context.execution_context, attempt)
            if last.status in {"completed", "skipped", "already_satisfied"}:
                return last
        assert last is not None
        return last

    def _append_receipt(self, operation: OperationRun, receipt: ActionReceipt) -> OperationRun:
        if receipt.status == "rolled_back":
            event_type = "action.rolled_back"
            action_status = "rolled_back"
        elif receipt.status in {"completed", "already_satisfied"}:
            event_type = "action.completed"
            action_status = "completed"
        elif receipt.status == "skipped":
            event_type = "action.completed"
            action_status = "skipped"
        else:
            event_type = "action.failed"
            action_status = "failed"
        actions = [
            item.model_copy(update={"status": action_status}) if item.action_id == receipt.action_id else item
            for item in operation.plan.actions
        ]
        operation = operation.model_copy(
            update={
                "plan": operation.plan.model_copy(update={"actions": actions}),
                "action_receipts": [*operation.action_receipts, receipt],
                "current_action_ids": [
                    item for item in operation.current_action_ids if item != receipt.action_id
                ],
                "updated_at_iso": utc_now_iso(),
                "events": [
                    *operation.events,
                    self._event(
                        operation.operation_id,
                        len(operation.events),
                        event_type,
                        f"{receipt.action_id}: {receipt.status}",
                        action_id=receipt.action_id,
                        details={
                            "receipt_id": receipt.receipt_id,
                            "executor_id": receipt.executor_id,
                        },
                    ),
                ],
            }
        )
        self.store.save(operation)
        return operation

    def _set_action_status(
        self,
        operation: OperationRun,
        action_id: str,
        status: str,
        *,
        current: bool = False,
    ) -> OperationRun:
        actions = [
            item.model_copy(update={"status": status}) if item.action_id == action_id else item
            for item in operation.plan.actions
        ]
        current_ids = [action_id] if current else [
            item for item in operation.current_action_ids if item != action_id
        ]
        events = list(operation.events)
        if current:
            events.append(
                self._event(
                    operation.operation_id,
                    len(events),
                    "action.started",
                    f"Action {action_id} started",
                    action_id=action_id,
                )
            )
        operation = operation.model_copy(
            update={
                "plan": operation.plan.model_copy(update={"actions": actions}),
                "current_action_ids": current_ids,
                "updated_at_iso": utc_now_iso(),
                "events": events,
            }
        )
        self.store.save(operation)
        return operation

    def _checkpoint(self, operation: OperationRun, world: dict[str, dict]) -> OperationRun:
        completed = [item.action_id for item in operation.action_receipts if item.status in {"completed", "already_satisfied", "skipped"}]
        pending = [item.action_id for item in operation.plan.actions if item.action_id not in completed]
        state_hash = hashlib.sha256(json.dumps(world, sort_keys=True, default=str).encode()).hexdigest()
        checkpoint = ExecutionCheckpoint(
            checkpoint_id=f"checkpoint:{operation.operation_id}:{len(operation.checkpoints)}",
            operation_id=operation.operation_id,
            created_at_iso=utc_now_iso(),
            completed_action_ids=completed,
            pending_action_ids=pending,
            world_state=world,
            state_hash=state_hash,
        )
        operation = operation.model_copy(update={"checkpoints": [*operation.checkpoints, checkpoint], "events": [*operation.events, self._event(operation.operation_id, len(operation.events), "checkpoint.created", "Execution checkpoint created", details={"checkpoint_id": checkpoint.checkpoint_id})], "updated_at_iso": utc_now_iso()})
        self.store.save(operation)
        return operation

    @staticmethod
    def _already_satisfied(operation: OperationRun, action: ActionInstance) -> ActionReceipt:
        now = utc_now_iso()
        return ActionReceipt(
            receipt_id=f"receipt:{operation.operation_id}:{action.action_id}:idempotent",
            operation_id=operation.operation_id, action_id=action.action_id, action_type_id=action.action_type_id,
            executor_id="idempotency_guard", status="already_satisfied", started_at_iso=now, completed_at_iso=now,
            stdout="matching idempotency key already completed", idempotency_key=action.idempotency_key,
        )

    @staticmethod
    def _fail(operation: OperationRun, reason: str) -> OperationRun:
        return operation.model_copy(update={"status": "failed", "failure_reason": reason, "updated_at_iso": utc_now_iso(), "events": [*operation.events, OperationRuntime._event(operation.operation_id, len(operation.events), "operation.failed", reason)]})

    @staticmethod
    def _event(operation_id: str, sequence: int, event_type: str, title: str, *, action_id: str | None = None, details: dict | None = None) -> OperationEvent:
        return OperationEvent(sequence=sequence, operation_id=operation_id, event_type=event_type, occurred_at_iso=utc_now_iso(), title=title, action_id=action_id, details=details or {})
