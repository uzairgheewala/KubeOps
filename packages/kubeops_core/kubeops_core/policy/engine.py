from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from datetime import datetime, timezone

from kubeops_core.models.operation import ApprovalRecord
from kubeops_core.models.planning import ActionInstance, ActionTypeDefinition, ExecutionPolicy, PolicyDecision
from kubeops_core.util import utc_now_iso

_RISK_ORDER = {f"R{i}": i for i in range(6)}


@dataclass(frozen=True)
class PolicyContext:
    environment_class: str
    environment_fingerprint: str | None = None
    expected_fingerprint: str | None = None
    capabilities: frozenset[str] = frozenset()
    mutation_count: int = 0
    break_glass: bool = False
    execution_mode: str = "simulation"


class PolicyEngine:
    def evaluate(
        self,
        action: ActionInstance,
        definition: ActionTypeDefinition,
        policy: ExecutionPolicy,
        context: PolicyContext,
        approvals: list[ApprovalRecord] | None = None,
    ) -> PolicyDecision:
        reasons: list[str] = []
        gaps = sorted(definition.required_capabilities - context.capabilities - policy.capability_grants)
        outcome = "allow"
        required = policy.required_approvals_by_risk.get(action.risk.risk_class, 0)

        if policy.environment_classes and context.environment_class not in policy.environment_classes:
            reasons.append(f"environment class {context.environment_class!r} is not covered by policy")
            outcome = "deny"
        if action.action_type_id in policy.denied_action_type_ids:
            reasons.append("action type is explicitly denied")
            outcome = "deny"
        if policy.allowed_action_type_ids and action.action_type_id not in policy.allowed_action_type_ids:
            reasons.append("action type is not in the policy allowlist")
            outcome = "deny"
        if action.risk.risk_class not in policy.allowed_risk_classes:
            reasons.append(f"risk class {action.risk.risk_class} is not allowed")
            outcome = "deny"
        if gaps:
            reasons.append(f"missing capabilities: {', '.join(gaps)}")
            outcome = "deny"
        if context.execution_mode != "dry_run" and context.execution_mode not in definition.supported_modes:
            reasons.append(
                f"action type does not support execution mode {context.execution_mode!r}"
            )
            outcome = "deny"
        if policy.require_target_fingerprint and context.expected_fingerprint:
            if context.environment_fingerprint != context.expected_fingerprint:
                reasons.append("target fingerprint does not match the registered environment")
                outcome = "deny"
        if policy.mutation_budget is not None and context.mutation_count >= policy.mutation_budget:
            reasons.append("mutation budget exhausted")
            outcome = "deny"
        if policy.allowed_target_patterns and action.target_ids:
            invalid = [target for target in action.target_ids if not any(fnmatch.fnmatch(target, pattern) for pattern in policy.allowed_target_patterns)]
            if invalid:
                reasons.append(f"targets outside policy scope: {', '.join(invalid)}")
                outcome = "deny"

        now = datetime.now(timezone.utc)
        applicable = [
            item for item in approvals or []
            if item.operation_id and item.action_id in {None, action.action_id}
        ]
        active: list[ApprovalRecord] = []
        for item in applicable:
            if item.expires_at_iso:
                try:
                    expires = datetime.fromisoformat(item.expires_at_iso.replace("Z", "+00:00"))
                except ValueError:
                    reasons.append(f"approval {item.approval_id} has an invalid expiration timestamp")
                    outcome = "deny"
                    continue
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires <= now:
                    continue
            active.append(item)

        rejecting_approvers = sorted({item.approver_id for item in active if item.decision == "reject"})
        if rejecting_approvers:
            reasons.append(f"execution rejected by: {', '.join(rejecting_approvers)}")
            outcome = "deny"

        approving_approvers = {item.approver_id for item in active if item.decision == "approve"}
        if outcome != "deny" and len(approving_approvers) < required:
            reasons.append(f"{required - len(approving_approvers)} additional distinct approval(s) required")
            outcome = "approval_required"
        if context.break_glass and not policy.break_glass_allowed:
            reasons.append("break-glass execution is not allowed by policy")
            outcome = "deny"
        if not reasons:
            reasons.append("action satisfies policy scope, risk, capability, and approval requirements")

        return PolicyDecision(
            decision_id=f"decision:{action.action_id}:{policy.policy_id}",
            policy_id=policy.policy_id,
            action_id=action.action_id,
            outcome=outcome,
            reasons=reasons,
            required_approval_count=required,
            evaluated_at_iso=utc_now_iso(),
            capability_gaps=gaps,
            requires_checkpoint=action.risk.risk_class in policy.require_checkpoint_for_risk or action.checkpoint_before,
            metadata={"risk_rank": _RISK_ORDER[action.risk.risk_class]},
        )
