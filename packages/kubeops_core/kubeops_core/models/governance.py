from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from .base import SchemaModel


class RateLimitRule(SchemaModel):
    kind: ClassVar[str] = "RateLimitRule"

    rule_id: str
    scope_type: str
    scope_id: str
    operation: str
    limit: int = Field(ge=1)
    window_seconds: int = Field(ge=1)
    burst: int = Field(default=0, ge=0)
    enabled: bool = True


class ConcurrencyRule(SchemaModel):
    kind: ClassVar[str] = "ConcurrencyRule"

    rule_id: str
    scope_type: str
    scope_id: str
    operation_type: str = "*"
    maximum_active: int = Field(ge=1)
    serialize_by_target: bool = True
    enabled: bool = True


class GovernanceDecision(SchemaModel):
    kind: ClassVar[str] = "GovernanceDecision"

    decision_id: str
    outcome: Literal["allow", "deny", "delay"]
    reasons: list[str] = Field(default_factory=list)
    retry_after_seconds: int | None = Field(default=None, ge=0)
    matched_rule_ids: list[str] = Field(default_factory=list)
    evaluated_at_iso: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetentionPolicy(SchemaModel):
    kind: ClassVar[str] = "RetentionPolicy"

    policy_id: str
    organization_id: str
    scope_type: str = "workspace"
    scope_id: str
    artifact_retention_days: int = Field(default=90, ge=1)
    audit_retention_days: int = Field(default=365, ge=1)
    snapshot_retention_days: int = Field(default=30, ge=1)
    incident_retention_days: int = Field(default=365, ge=1)
    operation_retention_days: int = Field(default=365, ge=1)
    preserve_failed_operations: bool = True
    preserve_certificates: bool = True
    legal_hold_labels: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetentionCandidate(SchemaModel):
    kind: ClassVar[str] = "RetentionCandidate"

    candidate_id: str
    resource_type: str
    resource_id: str
    created_at_iso: str
    expires_at_iso: str
    size_bytes: int = Field(default=0, ge=0)
    protected: bool = False
    protection_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetentionPlan(SchemaModel):
    kind: ClassVar[str] = "RetentionPlan"

    plan_id: str
    policy_id: str
    generated_at_iso: str
    candidates: list[RetentionCandidate] = Field(default_factory=list)
    eligible_candidate_ids: list[str] = Field(default_factory=list)
    protected_candidate_ids: list[str] = Field(default_factory=list)
    total_reclaimable_bytes: int = Field(default=0, ge=0)
    dry_run: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEvent(SchemaModel):
    kind: ClassVar[str] = "AuditEvent"

    event_id: str
    sequence: int = Field(ge=0)
    organization_id: str
    workspace_id: str
    principal_id: str
    action: str
    resource_type: str
    resource_id: str
    outcome: str
    occurred_at_iso: str
    request_id: str | None = None
    source_ip: str | None = None
    user_agent: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str | None = None
    event_hash: str


class AuditChainVerification(SchemaModel):
    kind: ClassVar[str] = "AuditChainVerification"

    valid: bool
    event_count: int = Field(ge=0)
    first_sequence: int | None = None
    last_sequence: int | None = None
    head_hash: str | None = None
    errors: list[str] = Field(default_factory=list)
    verified_at_iso: str


class AuditExport(SchemaModel):
    kind: ClassVar[str] = "AuditExport"

    export_id: str
    organization_id: str
    workspace_id: str
    generated_at_iso: str
    event_ids: list[str]
    first_sequence: int | None = None
    last_sequence: int | None = None
    head_hash: str | None = None
    format: Literal["jsonl", "json"] = "jsonl"
    payload_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)
