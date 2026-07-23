from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from kubeops_core.models import ConcurrencyRule, GovernanceDecision, RateLimitRule

from .models import (
    ConcurrencyRuleRecord,
    GovernanceUsageRecord,
    RateLimitRuleRecord,
    WorkspaceRecord,
)


def evaluate_governance(
    *,
    workspace: WorkspaceRecord,
    operation: str,
    active_count: int,
    target_id: str | None = None,
    record_usage: bool = True,
) -> GovernanceDecision:
    """Evaluate durable workspace rate and concurrency rules under one DB lock."""

    with transaction.atomic():
        locked_workspace = WorkspaceRecord.objects.select_for_update().get(pk=workspace.pk)
        now = timezone.now()
        reasons: list[str] = []
        matched: list[str] = []
        retry_after: int | None = None

        for record in RateLimitRuleRecord.objects.filter(workspace=locked_workspace, enabled=True):
            rule = RateLimitRule.model_validate(record.payload)
            if rule.operation not in {operation, "*"}:
                continue
            matched.append(rule.rule_id)
            cutoff = now - timedelta(seconds=rule.window_seconds)
            usage = GovernanceUsageRecord.objects.filter(
                workspace=locked_workspace,
                operation=operation,
                occurred_at__gt=cutoff,
            ).order_by("occurred_at")
            count = usage.count()
            if count >= rule.limit + rule.burst:
                oldest = usage.first()
                if oldest is not None:
                    retry_after = max(
                        retry_after or 0,
                        max(0, int((oldest.occurred_at + timedelta(seconds=rule.window_seconds) - now).total_seconds())),
                    )
                reasons.append(f"rate limit {rule.rule_id} exceeded")

        for record in ConcurrencyRuleRecord.objects.filter(workspace=locked_workspace, enabled=True):
            rule = ConcurrencyRule.model_validate(record.payload)
            if rule.operation_type not in {operation, "*"}:
                continue
            matched.append(rule.rule_id)
            if active_count >= rule.maximum_active:
                reasons.append(f"concurrency limit {rule.rule_id} reached")
            if rule.serialize_by_target and target_id:
                if GovernanceUsageRecord.objects.filter(
                    workspace=locked_workspace,
                    operation=operation,
                    target_id=target_id,
                    terminal=False,
                ).exists():
                    reasons.append(f"target serialization required by {rule.rule_id}")

        outcome = "delay" if reasons else "allow"
        decision = GovernanceDecision(
            decision_id=f"governance:{uuid4()}",
            outcome=outcome,
            reasons=reasons,
            retry_after_seconds=retry_after,
            matched_rule_ids=sorted(set(matched)),
            evaluated_at_iso=now.isoformat(),
            metadata={"operation": operation, "active_count": active_count, "target_id": target_id},
        )
        if outcome == "allow" and record_usage and matched:
            GovernanceUsageRecord.objects.create(
                usage_id=f"usage:{uuid4()}",
                workspace=locked_workspace,
                operation=operation,
                target_id=target_id,
                decision_id=decision.decision_id,
                occurred_at=now,
                terminal=False,
                payload=decision.model_dump(mode="json"),
            )
        return decision


def mark_governance_usage_terminal(*, workspace: WorkspaceRecord, operation: str, target_id: str) -> int:
    return GovernanceUsageRecord.objects.filter(
        workspace=workspace,
        operation=operation,
        target_id=target_id,
        terminal=False,
    ).update(terminal=True)
