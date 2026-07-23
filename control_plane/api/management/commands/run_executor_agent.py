from __future__ import annotations

import hashlib
import json
import os
import signal
import time
from datetime import datetime, timedelta
from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from kubeops_core.execution import ExecutionContext, build_default_executor_registry
from kubeops_core.models import (
    ActionInstance, ActionReceipt, ActionTypeDefinition, ExecutionTask, ExecutorAgentDefinition, OperationRun,
)
from kubeops_core.util import utc_now_iso

from api.models import (
    ActionReceiptRecord,
    ExecutionTaskRecord,
    ExecutorAgentRecord,
    ExecutorHeartbeatRecord,
    OrganizationRecord,
    OperationRecord,
    TaskLeaseRecord,
    WorkspaceRecord,
)
from api.services import action_catalog_for_workspace, operation_runtime_for_workspace


class Command(BaseCommand):
    help = "Run a durable capability-scoped KubeOps distributed executor agent."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--agent-id", default=os.getenv("KUBEOPS_EXECUTOR_AGENT_ID", "executor-local"))
        parser.add_argument("--name", default=os.getenv("KUBEOPS_EXECUTOR_AGENT_NAME", "Local executor"))
        parser.add_argument("--organization-id", default=os.getenv("KUBEOPS_DEFAULT_ORGANIZATION_ID", "default"))
        parser.add_argument("--workspace-id", default=os.getenv("KUBEOPS_DEFAULT_WORKSPACE_ID", "default"))
        parser.add_argument("--capabilities", default=os.getenv("KUBEOPS_EXECUTOR_CAPABILITIES", "executor.claim,executor.complete"))
        parser.add_argument("--executors", default=os.getenv("KUBEOPS_EXECUTOR_IDS", "dry_run,simulation,builtin.wait"))
        parser.add_argument("--environments", default=os.getenv("KUBEOPS_EXECUTOR_ENVIRONMENTS", ""))
        parser.add_argument("--max-concurrency", type=int, default=int(os.getenv("KUBEOPS_EXECUTOR_MAX_CONCURRENCY", "1")))
        parser.add_argument("--poll-seconds", type=float, default=float(os.getenv("KUBEOPS_EXECUTOR_POLL_SECONDS", "2")))
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        if options["max_concurrency"] < 1:
            raise CommandError("--max-concurrency must be at least 1")
        self.stop_requested = False
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stop_requested", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "stop_requested", True))
        capabilities = {item.strip() for item in options["capabilities"].split(",") if item.strip()}
        executor_ids = {item.strip() for item in options["executors"].split(",") if item.strip()}
        environments = {item.strip() for item in options["environments"].split(",") if item.strip()}
        agent = self._register_agent(options, capabilities, executor_ids, environments)
        self.stdout.write(self.style.SUCCESS(f"executor agent {agent.agent_id} registered"))
        while not self.stop_requested:
            self._expire_stale_leases()
            self._heartbeat(agent)
            processed = self._process_one(agent)
            if options["once"]:
                break
            if not processed:
                time.sleep(options["poll_seconds"])
        agent.status = "offline"
        payload = dict(agent.payload)
        payload["status"] = "offline"
        payload["last_heartbeat_at_iso"] = utc_now_iso()
        agent.payload = payload
        agent.last_heartbeat_at = timezone.now()
        agent.save(update_fields=["status", "payload", "last_heartbeat_at", "updated_at"])
        self.stdout.write(self.style.WARNING(f"executor agent {agent.agent_id} stopped"))

    def _register_agent(self, options, capabilities: set[str], executor_ids: set[str], environments: set[str]) -> ExecutorAgentRecord:  # type: ignore[no-untyped-def]
        organization = OrganizationRecord.objects.get(organization_id=options["organization_id"])
        workspace = WorkspaceRecord.objects.get(workspace_id=options["workspace_id"])
        now = utc_now_iso()
        definition = ExecutorAgentDefinition(
            agent_id=options["agent_id"], organization_id=organization.organization_id,
            workspace_id=workspace.workspace_id, name=options["name"], status="online",
            capabilities=capabilities, supported_executor_ids=executor_ids,
            environment_ids=environments, max_concurrency=options["max_concurrency"],
            registered_at_iso=now, last_heartbeat_at_iso=now,
            public_identity=f"django-agent:{options['agent_id']}",
        )
        existing = ExecutorAgentRecord.objects.filter(agent_id=definition.agent_id).first()
        if existing is not None and (
            existing.organization_id != organization.pk
            or existing.workspace_id != workspace.pk
            or existing.public_identity != definition.public_identity
        ):
            raise CommandError(
                f"agent {definition.agent_id!r} is already bound to a different tenant or public identity"
            )
        record, _ = ExecutorAgentRecord.objects.update_or_create(
            agent_id=definition.agent_id,
            defaults={
                "organization": organization, "workspace": workspace, "name": definition.name,
                "status": definition.status, "capabilities": sorted(definition.capabilities),
                "supported_executor_ids": sorted(definition.supported_executor_ids),
                "environment_ids": sorted(definition.environment_ids), "max_concurrency": definition.max_concurrency,
                "last_heartbeat_at": timezone.now(), "public_identity": definition.public_identity,
                "payload": definition.model_dump(mode="json"),
            },
        )
        return record

    def _heartbeat(self, agent: ExecutorAgentRecord) -> None:
        active_ids = list(TaskLeaseRecord.objects.filter(agent=agent, status="active").values_list("task__task_id", flat=True))
        now = timezone.now()
        available_capacity = max(0, agent.max_concurrency - len(active_ids))
        payload = dict(agent.payload)
        payload.update({
            "status": "online",
            "last_heartbeat_at_iso": now.isoformat(),
            "available_capacity": available_capacity,
            "active_task_ids": active_ids,
        })
        agent.status = "online"
        agent.last_heartbeat_at = now
        agent.payload = payload
        agent.save(update_fields=["status", "last_heartbeat_at", "payload", "updated_at"])
        heartbeat_id = f"heartbeat:{agent.agent_id}:{uuid4()}"
        ExecutorHeartbeatRecord.objects.create(
            heartbeat_id=heartbeat_id, agent=agent, status="online", occurred_at=now,
            payload={
                "heartbeat_id": heartbeat_id, "agent_id": agent.agent_id,
                "occurred_at_iso": now.isoformat(), "status": "online", "active_task_ids": active_ids,
                "available_capacity": available_capacity,
                "capabilities": agent.capabilities, "diagnostics": {},
            },
        )

    def _expire_stale_leases(self) -> None:
        now = timezone.now()
        affected_operations = set()
        with transaction.atomic():
            leases = list(
                TaskLeaseRecord.objects.select_for_update(skip_locked=True)
                .filter(status="active", expires_at__lte=now)
                .select_related("task__operation")
            )
            for lease in leases:
                lease.status = "expired"
                lease.heartbeat_at = now
                lease.save(update_fields=["status", "heartbeat_at"])
                task = lease.task
                model = ExecutionTask.model_validate(task.payload)
                next_attempt = model.attempt + 1
                if next_attempt <= model.max_attempts:
                    task.status = "queued"
                    task.assigned_agent = None
                    task.payload = model.model_copy(
                        update={
                            "status": "queued",
                            "attempt": next_attempt,
                            "assigned_agent_id": None,
                            "updated_at_iso": now.isoformat(),
                        }
                    ).model_dump(mode="json")
                else:
                    task.status = "failed"
                    task.payload = model.model_copy(
                        update={
                            "status": "failed",
                            "updated_at_iso": now.isoformat(),
                            "metadata": {**model.metadata, "failure_reason": "executor lease expired"},
                        }
                    ).model_dump(mode="json")
                    failure = ActionReceipt(
                        receipt_id=f"receipt:{task.operation.operation_id}:{task.action_id}:{model.attempt}:lease-expired",
                        operation_id=task.operation.operation_id, action_id=task.action_id,
                        action_type_id=task.action_type_id, executor_id=task.executor_id, status="failed",
                        attempt=model.attempt, started_at_iso=lease.acquired_at.isoformat(),
                        completed_at_iso=now.isoformat(), stderr="executor lease expired",
                        metadata={"lease_id": lease.lease_id},
                    )
                    ActionReceiptRecord.objects.update_or_create(
                        receipt_id=failure.receipt_id,
                        defaults={
                            "operation": task.operation, "action_id": failure.action_id,
                            "action_type_id": failure.action_type_id, "executor_id": failure.executor_id,
                            "status": failure.status, "attempt": failure.attempt,
                            "started_at": lease.acquired_at, "completed_at": now,
                            "idempotency_key": failure.idempotency_key,
                            "payload": failure.model_dump(mode="json"),
                        },
                    )
                task.updated_at = now
                task.save(update_fields=["status", "assigned_agent", "payload", "updated_at"])
                affected_operations.add(task.operation.operation_id)
        for operation_id in affected_operations:
            self._reconcile_operation(OperationRecord.objects.get(operation_id=operation_id))

    def _process_one(self, agent: ExecutorAgentRecord) -> bool:
        active = TaskLeaseRecord.objects.filter(agent=agent, status="active").count()
        if active >= agent.max_concurrency:
            return False
        self._cancel_blocked_tasks()
        with transaction.atomic():
            tasks = ExecutionTaskRecord.objects.select_for_update(skip_locked=True).filter(status="queued").order_by("-priority", "created_at")
            task = next((item for item in tasks if self._matches(agent, item)), None)
            if task is None:
                return False
            now = timezone.now()
            nonce = uuid4().hex
            execution_payload = task.payload.get("payload", {})
            timeout_seconds = int(execution_payload.get("execution_context", {}).get("command_timeout_seconds", 120))
            lease_ttl = max(int(agent.payload.get("lease_ttl_seconds", 60)), timeout_seconds + 30)
            lease = TaskLeaseRecord.objects.create(
                lease_id=f"lease:{task.task_id}:{uuid4()}", task=task, agent=agent, status="active",
                nonce_hash=hashlib.sha256(nonce.encode()).hexdigest(), acquired_at=now,
                expires_at=now + timedelta(seconds=lease_ttl), heartbeat_at=now,
                payload={"task_id": task.task_id, "agent_id": agent.agent_id, "acquired_at_iso": now.isoformat()},
            )
            task.status = "running"
            task.assigned_agent = agent
            payload = dict(task.payload)
            payload.update({"status": "running", "assigned_agent_id": agent.agent_id, "updated_at_iso": now.isoformat()})
            task.payload = payload
            task.updated_at = now
            task.save(update_fields=["status", "assigned_agent", "payload", "updated_at"])
        self._reconcile_operation(task.operation)
        self._execute(task, lease, nonce)
        return True

    @staticmethod
    def _matches(agent: ExecutorAgentRecord, task: ExecutionTaskRecord) -> bool:
        if task.executor_id not in set(agent.supported_executor_ids):
            return False
        if agent.environment_ids and task.environment_id not in set(agent.environment_ids):
            return False
        required = set(task.payload.get("required_capabilities", []))
        if not required <= set(agent.capabilities):
            return False
        execution_payload = task.payload.get("payload", {})
        dependencies = set(execution_payload.get("depends_on_action_ids", []))
        if dependencies:
            completed = set(
                task.operation.execution_tasks.filter(
                    action_id__in=dependencies, status="completed"
                ).values_list("action_id", flat=True)
            )
            if not dependencies <= completed:
                return False
        return True

    @staticmethod
    def _cancel_blocked_tasks() -> None:
        queued = ExecutionTaskRecord.objects.filter(status="queued").select_related("operation")
        now = timezone.now()
        for task in queued:
            execution_payload = task.payload.get("payload", {})
            dependencies = set(execution_payload.get("depends_on_action_ids", []))
            dependency_failed = task.operation.execution_tasks.filter(
                action_id__in=dependencies, status__in=["failed", "cancelled"]
            ).exists()
            operation_terminal = task.operation.status in {"failed", "cancelled", "completed"}
            if dependency_failed or operation_terminal:
                task.status = "cancelled"
                task.updated_at = now
                task.payload = {
                    **task.payload,
                    "status": "cancelled",
                    "updated_at_iso": now.isoformat(),
                    "cancellation_reason": (
                        "dependency failed" if dependency_failed else "operation is terminal"
                    ),
                }
                task.save(update_fields=["status", "updated_at", "payload"])

    def _execute(self, task: ExecutionTaskRecord, lease: TaskLeaseRecord, nonce: str) -> None:
        success = False
        nonce_verified = hashlib.sha256(nonce.encode()).hexdigest() == lease.nonce_hash
        try:
            if not nonce_verified:
                raise PermissionError("task lease nonce verification failed")
            task_model = ExecutionTask.model_validate(task.payload)
            payload = task_model.payload
            calculated_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if calculated_hash != task_model.payload_hash or calculated_hash != task.payload_hash:
                raise ValueError("distributed task payload hash mismatch")
            action = ActionInstance.model_validate(payload["action"])
            supplied_definition = ActionTypeDefinition.model_validate(payload["action_definition"])
            definition = action_catalog_for_workspace(task.workspace_id).validate_instance(action)
            if supplied_definition.content_hash != definition.content_hash:
                raise ValueError("distributed task action definition is not authoritative")
            if action.action_id != task.action_id or action.action_type_id != task.action_type_id:
                raise ValueError("distributed task action identity mismatch")
            requested_mode = str(payload.get("mode", "dry_run"))
            expected_executor = (
                "dry_run" if requested_mode == "dry_run"
                else "simulation" if requested_mode == "simulation"
                else definition.executor_id
            )
            if task.executor_id != expected_executor:
                raise ValueError("distributed task executor does not match its execution mode")
            if requested_mode == "live" and "live" not in definition.supported_modes:
                raise PermissionError("action does not support live execution")
            if requested_mode == "simulation" and "simulation" not in definition.supported_modes:
                raise PermissionError("action does not support simulation")
            if task_model.target_fingerprint and task_model.target_fingerprint != task.environment.fingerprint:
                raise PermissionError("distributed task target fingerprint mismatch")
            if requested_mode == "live" and not settings.KUBEOPS_LIVE_EXECUTION_ENABLED:
                raise PermissionError("live execution is disabled by the server-wide safety gate")
            context_payload = dict(payload.get("execution_context", {}))
            context = ExecutionContext(
                operation_id=task.operation.operation_id, mode=requested_mode,
                environment_id=task.environment.environment_id,
                working_directory=None,
                executable_allowlist=set(context_payload.get("executable_allowlist", ["docker", "kubectl", "systemctl", "service", "kill"])),
                command_timeout_seconds=int(context_payload.get("command_timeout_seconds", 120)),
                metadata={"distributed_task_id": task.task_id, "agent_id": lease.agent.agent_id},
            )
            executor = build_default_executor_registry().get(task.executor_id)
            receipt = executor.execute(action, definition, context, task_model.attempt)
            ActionReceiptRecord.objects.update_or_create(
                receipt_id=receipt.receipt_id,
                defaults={
                    "operation": task.operation, "action_id": receipt.action_id, "action_type_id": receipt.action_type_id,
                    "executor_id": receipt.executor_id, "status": receipt.status, "attempt": receipt.attempt,
                    "started_at": datetime.fromisoformat(receipt.started_at_iso.replace("Z", "+00:00")),
                    "completed_at": datetime.fromisoformat(receipt.completed_at_iso.replace("Z", "+00:00")),
                    "idempotency_key": receipt.idempotency_key, "payload": receipt.model_dump(mode="json"),
                },
            )
            success = receipt.status in {"completed", "already_satisfied", "skipped"}
        except Exception as exc:  # noqa: BLE001 - persisted as a bounded task failure
            now_iso = utc_now_iso()
            error = f"{type(exc).__name__}: {exc}"
            task.payload = {**task.payload, "executor_error": error}
            failure_receipt = ActionReceipt(
                receipt_id=f"receipt:{task.operation.operation_id}:{task.action_id}:{task.payload.get('attempt', 1)}:failed",
                operation_id=task.operation.operation_id,
                action_id=task.action_id,
                action_type_id=task.action_type_id,
                executor_id=task.executor_id,
                status="failed",
                attempt=int(task.payload.get("attempt", 1)),
                started_at_iso=now_iso,
                completed_at_iso=now_iso,
                stderr=error,
                metadata={"distributed_task_id": task.task_id, "agent_id": lease.agent.agent_id},
            )
            ActionReceiptRecord.objects.update_or_create(
                receipt_id=failure_receipt.receipt_id,
                defaults={
                    "operation": task.operation,
                    "action_id": failure_receipt.action_id,
                    "action_type_id": failure_receipt.action_type_id,
                    "executor_id": failure_receipt.executor_id,
                    "status": failure_receipt.status,
                    "attempt": failure_receipt.attempt,
                    "started_at": datetime.fromisoformat(now_iso.replace("Z", "+00:00")),
                    "completed_at": datetime.fromisoformat(now_iso.replace("Z", "+00:00")),
                    "idempotency_key": failure_receipt.idempotency_key,
                    "payload": failure_receipt.model_dump(mode="json"),
                },
            )
        finally:
            now = timezone.now()
            lease.status = "released"
            lease.heartbeat_at = now
            lease.save(update_fields=["status", "heartbeat_at"])
            task.status = "completed" if success else "failed"
            task.updated_at = now
            task.payload = {**task.payload, "status": task.status, "updated_at_iso": now.isoformat(), "lease_nonce_verified": nonce_verified}
            task.save(update_fields=["status", "updated_at", "payload"])
            self._reconcile_operation(task.operation)

    def _reconcile_operation(self, operation_record) -> None:  # type: ignore[no-untyped-def]
        operation_record.refresh_from_db()
        operation = OperationRun.model_validate(operation_record.payload)
        receipts = [
            ActionReceipt.model_validate(item.payload)
            for item in operation_record.action_receipts.order_by("started_at", "receipt_id")
        ]
        current = list(
            operation_record.execution_tasks.filter(status="running").values_list("action_id", flat=True)
        )
        workspace = operation_record.environment.workspace
        if workspace is None:
            raise ValueError("distributed operation environment has no workspace scope")
        reconciled = operation_runtime_for_workspace(workspace.workspace_id).reconcile_external_receipts(
            operation, receipts, current_action_ids=current
        )
        if reconciled.status == "failed":
            now = timezone.now()
            for pending in operation_record.execution_tasks.filter(status="queued"):
                pending.status = "cancelled"
                pending.updated_at = now
                pending.payload = {
                    **pending.payload,
                    "status": "cancelled",
                    "updated_at_iso": now.isoformat(),
                    "cancellation_reason": "another required action failed",
                }
                pending.save(update_fields=["status", "updated_at", "payload"])
        if reconciled.status in {"verifying", "failed", "completed", "cancelled"}:
            from api.governance import mark_governance_usage_terminal

            mark_governance_usage_terminal(
                workspace=workspace, operation="operation.dispatch", target_id=operation.operation_id
            )
        from api.views import _persist_operation

        _persist_operation(
            reconciled,
            operation_record.environment,
            snapshot_record=operation_record.snapshot,
            incident_record=operation_record.incident,
        )
