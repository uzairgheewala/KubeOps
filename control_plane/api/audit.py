from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from kubeops_core.models import AuditEvent

from .models import AuditEventRecord, OrganizationRecord, WorkspaceRecord


def append_audit_event(
    *,
    organization: OrganizationRecord,
    workspace: WorkspaceRecord,
    principal_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    outcome: str,
    details: dict | None = None,
    request_id: str | None = None,
    source_ip: str | None = None,
    user_agent: str | None = None,
) -> AuditEventRecord:
    """Append one event while serializing the chain head per workspace."""

    with transaction.atomic():
        locked_workspace = WorkspaceRecord.objects.select_for_update().get(pk=workspace.pk)
        last = (
            AuditEventRecord.objects.filter(workspace=locked_workspace)
            .order_by("-sequence")
            .first()
        )
        sequence = (last.sequence + 1) if last else 0
        previous_hash = last.event_hash if last else None
        occurred_at = timezone.now()
        base = {
            "schema_version": "kubeops.io/v1",
            "event_id": f"audit:{uuid4()}",
            "sequence": sequence,
            "organization_id": organization.organization_id,
            "workspace_id": locked_workspace.workspace_id,
            "principal_id": principal_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "outcome": outcome,
            "occurred_at_iso": occurred_at.isoformat(),
            "request_id": request_id,
            "source_ip": source_ip,
            "user_agent": user_agent,
            "details": details or {},
            "previous_hash": previous_hash,
        }
        event_hash = hashlib.sha256(
            json.dumps(base, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        event = AuditEvent(**base, event_hash=event_hash)
        return AuditEventRecord.objects.create(
            event_id=event.event_id,
            organization=organization,
            workspace=locked_workspace,
            sequence=sequence,
            principal_id=principal_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            previous_hash=previous_hash,
            event_hash=event_hash,
            occurred_at=occurred_at,
            payload=event.model_dump(mode="json"),
        )
