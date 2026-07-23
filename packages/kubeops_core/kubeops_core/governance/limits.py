from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from kubeops_core.models.governance import ConcurrencyRule, GovernanceDecision, RateLimitRule


class GovernanceLimiter:
    def __init__(self, rate_rules: list[RateLimitRule] | None = None, concurrency_rules: list[ConcurrencyRule] | None = None) -> None:
        self.rate_rules = rate_rules or []
        self.concurrency_rules = concurrency_rules or []
        self.usage: dict[str, list[datetime]] = {}

    def evaluate(
        self,
        *,
        scope_type: str,
        scope_id: str,
        operation: str,
        active_count: int = 0,
        at: datetime | None = None,
    ) -> GovernanceDecision:
        now = at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)
        reasons: list[str] = []
        matched: list[str] = []
        retry_after: int | None = None
        for rule in self.rate_rules:
            if not rule.enabled or (rule.scope_type, rule.scope_id) != (scope_type, scope_id) or rule.operation not in {operation, "*"}:
                continue
            matched.append(rule.rule_id)
            bucket = self.usage.setdefault(rule.rule_id, [])
            cutoff = now - timedelta(seconds=rule.window_seconds)
            bucket[:] = [item for item in bucket if item > cutoff]
            if len(bucket) >= rule.limit + rule.burst:
                retry_after = max(0, int((min(bucket) + timedelta(seconds=rule.window_seconds) - now).total_seconds()))
                reasons.append(f"rate limit {rule.rule_id} exceeded")
        for rule in self.concurrency_rules:
            if not rule.enabled or (rule.scope_type, rule.scope_id) != (scope_type, scope_id) or rule.operation_type not in {operation, "*"}:
                continue
            matched.append(rule.rule_id)
            if active_count >= rule.maximum_active:
                reasons.append(f"concurrency limit {rule.rule_id} reached")
        outcome = "delay" if reasons else "allow"
        if not reasons:
            for rule_id in matched:
                if rule_id in self.usage:
                    self.usage[rule_id].append(now)
        return GovernanceDecision(
            decision_id=f"governance:{uuid4()}", outcome=outcome, reasons=reasons,
            retry_after_seconds=retry_after, matched_rule_ids=matched, evaluated_at_iso=now.isoformat(),
        )
