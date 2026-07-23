from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from kubeops_core.models.governance import RetentionCandidate, RetentionPlan, RetentionPolicy


class RetentionPlanner:
    _FIELD_BY_TYPE = {
        "artifact": "artifact_retention_days",
        "audit": "audit_retention_days",
        "snapshot": "snapshot_retention_days",
        "incident": "incident_retention_days",
        "operation": "operation_retention_days",
    }

    def plan(self, policy: RetentionPolicy, resources: list[dict[str, object]], *, at: datetime | None = None) -> RetentionPlan:
        now = at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)
        candidates: list[RetentionCandidate] = []
        for resource in resources:
            resource_type = str(resource["resource_type"])
            field = self._FIELD_BY_TYPE.get(resource_type, "artifact_retention_days")
            days = int(getattr(policy, field))
            created = datetime.fromisoformat(str(resource["created_at_iso"]).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            else:
                created = created.astimezone(timezone.utc)
            expiry = created + timedelta(days=days)
            labels = dict(resource.get("labels", {}))
            reasons: list[str] = []
            if policy.preserve_failed_operations and resource_type == "operation" and resource.get("status") == "failed":
                reasons.append("failed operation preservation policy")
            if policy.preserve_certificates and bool(resource.get("has_certificate")):
                reasons.append("certificate preservation policy")
            if policy.legal_hold_labels and all(labels.get(key) == value for key, value in policy.legal_hold_labels.items()):
                reasons.append("legal hold label match")
            candidates.append(RetentionCandidate(
                candidate_id=f"retention:{resource_type}:{resource['resource_id']}", resource_type=resource_type,
                resource_id=str(resource["resource_id"]), created_at_iso=created.isoformat(), expires_at_iso=expiry.isoformat(),
                size_bytes=int(resource.get("size_bytes", 0)), protected=bool(reasons), protection_reasons=reasons,
                metadata={"expired": expiry <= now},
            ))
        eligible = [item.candidate_id for item in candidates if not item.protected and bool(item.metadata.get("expired"))]
        protected = [item.candidate_id for item in candidates if item.protected]
        reclaimable = sum(item.size_bytes for item in candidates if item.candidate_id in eligible)
        return RetentionPlan(
            plan_id=f"retention-plan:{uuid4()}", policy_id=policy.policy_id, generated_at_iso=now.isoformat(),
            candidates=candidates, eligible_candidate_ids=eligible, protected_candidate_ids=protected,
            total_reclaimable_bytes=reclaimable, dry_run=True,
        )
