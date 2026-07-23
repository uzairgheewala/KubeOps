from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from kubeops_core.models.governance import AuditChainVerification, AuditEvent, AuditExport
from kubeops_core.util import utc_now_iso


class AuditChain:
    def __init__(self, events: list[AuditEvent] | None = None) -> None:
        self.events = list(events or [])

    @staticmethod
    def _hash(payload: dict[str, object]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

    def append(
        self,
        *,
        organization_id: str,
        workspace_id: str,
        principal_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        outcome: str,
        request_id: str | None = None,
        source_ip: str | None = None,
        user_agent: str | None = None,
        details: dict[str, object] | None = None,
        occurred_at_iso: str | None = None,
    ) -> AuditEvent:
        previous_hash = self.events[-1].event_hash if self.events else None
        base = {
            "event_id": f"audit:{uuid4()}",
            "sequence": len(self.events),
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "principal_id": principal_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "outcome": outcome,
            "occurred_at_iso": occurred_at_iso or utc_now_iso(),
            "request_id": request_id,
            "source_ip": source_ip,
            "user_agent": user_agent,
            "details": details or {},
            "previous_hash": previous_hash,
        }
        event_hash = self._hash({"schema_version": "kubeops.io/v1", **base})
        event = AuditEvent(**base, event_hash=event_hash)
        self.events.append(event)
        return event

    def verify(self) -> AuditChainVerification:
        errors: list[str] = []
        previous: str | None = None
        for index, event in enumerate(self.events):
            if event.sequence != index:
                errors.append(f"event {event.event_id} sequence {event.sequence} expected {index}")
            if event.previous_hash != previous:
                errors.append(f"event {event.event_id} previous hash mismatch")
            payload = event.model_dump(mode="json", exclude={"event_hash"})
            if self._hash(payload) != event.event_hash:
                errors.append(f"event {event.event_id} hash mismatch")
            previous = event.event_hash
        return AuditChainVerification(
            valid=not errors,
            event_count=len(self.events),
            first_sequence=self.events[0].sequence if self.events else None,
            last_sequence=self.events[-1].sequence if self.events else None,
            head_hash=previous,
            errors=errors,
            verified_at_iso=utc_now_iso(),
        )

    def export(self, organization_id: str, workspace_id: str, *, format: str = "jsonl") -> tuple[AuditExport, str]:
        selected = [item for item in self.events if item.organization_id == organization_id and item.workspace_id == workspace_id]
        if format == "jsonl":
            payload = "\n".join(item.canonical_json() for item in selected) + ("\n" if selected else "")
        else:
            payload = json.dumps([item.canonical_dict() for item in selected], sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()
        export = AuditExport(
            export_id=f"audit-export:{uuid4()}", organization_id=organization_id, workspace_id=workspace_id,
            generated_at_iso=utc_now_iso(), event_ids=[item.event_id for item in selected],
            first_sequence=selected[0].sequence if selected else None, last_sequence=selected[-1].sequence if selected else None,
            head_hash=selected[-1].event_hash if selected else None, format=format, payload_hash=payload_hash,
        )
        return export, payload
