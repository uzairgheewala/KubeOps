from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from .base import SchemaModel
from .planning import ActionInstance, PolicyDecision, RecoveryPlan
from .verification import RecoveryCertificate, VerificationResult


OperationStatus = Literal[
    "created", "planning", "awaiting_approval", "authorized", "running", "paused",
    "verifying", "rolling_back", "completed", "failed", "cancelled", "blocked",
]
ActionReceiptStatus = Literal["completed", "failed", "skipped", "already_satisfied", "rolled_back"]


class ApprovalRecord(SchemaModel):
    kind: ClassVar[str] = "ApprovalRecord"

    approval_id: str
    operation_id: str
    action_id: str | None = None
    approver_id: str
    decision: Literal["approve", "reject"]
    reason: str = ""
    granted_at_iso: str
    expires_at_iso: str | None = None
    policy_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionReceipt(SchemaModel):
    kind: ClassVar[str] = "ActionReceipt"

    receipt_id: str
    operation_id: str
    action_id: str
    action_type_id: str
    executor_id: str
    status: ActionReceiptStatus
    attempt: int = Field(default=1, ge=1)
    started_at_iso: str
    completed_at_iso: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    observed_effects: list[str] = Field(default_factory=list)
    emitted_evidence_ids: list[str] = Field(default_factory=list)
    idempotency_key: str | None = None
    precondition_results: dict[str, bool | None] = Field(default_factory=dict)
    before_state_hash: str | None = None
    after_state_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperationEvent(SchemaModel):
    kind: ClassVar[str] = "OperationEvent"

    sequence: int = Field(ge=0)
    operation_id: str
    event_type: str
    occurred_at_iso: str
    title: str
    action_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionCheckpoint(SchemaModel):
    kind: ClassVar[str] = "ExecutionCheckpoint"

    checkpoint_id: str
    operation_id: str
    created_at_iso: str
    completed_action_ids: list[str] = Field(default_factory=list)
    pending_action_ids: list[str] = Field(default_factory=list)
    failed_action_ids: list[str] = Field(default_factory=list)
    world_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    state_hash: str
    resumable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperationRun(SchemaModel):
    kind: ClassVar[str] = "OperationRun"

    operation_id: str
    environment_id: str
    operation_type: Literal["startup", "shutdown", "recovery", "maintenance", "verification"]
    objective_id: str
    status: OperationStatus = "created"
    mode: Literal["dry_run", "guarded_execution"] = "dry_run"
    plan: RecoveryPlan
    policy_decisions: list[PolicyDecision] = Field(default_factory=list)
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    action_receipts: list[ActionReceipt] = Field(default_factory=list)
    verification_results: list[VerificationResult] = Field(default_factory=list)
    recovery_certificate: RecoveryCertificate | None = None
    events: list[OperationEvent] = Field(default_factory=list)
    checkpoints: list[ExecutionCheckpoint] = Field(default_factory=list)
    current_action_ids: list[str] = Field(default_factory=list)
    created_at_iso: str
    updated_at_iso: str
    started_at_iso: str | None = None
    completed_at_iso: str | None = None
    pause_reason: str | None = None
    failure_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_receipts(self) -> "OperationRun":
        plan_actions = {item.action_id for item in self.plan.actions}
        unknown = {item.action_id for item in self.action_receipts} - plan_actions
        if unknown:
            raise ValueError(f"operation receipts reference unknown actions: {sorted(unknown)}")
        return self
