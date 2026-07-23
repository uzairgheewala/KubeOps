from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from .base import SchemaModel

AgentStatus = Literal["registering", "online", "degraded", "draining", "offline", "revoked"]
TaskStatus = Literal["queued", "leased", "running", "completed", "failed", "cancelled", "expired"]
LeaseStatus = Literal["active", "released", "expired", "revoked"]


class ExecutorAgentDefinition(SchemaModel):
    kind: ClassVar[str] = "ExecutorAgentDefinition"

    agent_id: str
    organization_id: str
    workspace_id: str
    name: str
    status: AgentStatus = "registering"
    capabilities: set[str] = Field(default_factory=set)
    supported_executor_ids: set[str] = Field(default_factory=set)
    environment_ids: set[str] = Field(default_factory=set)
    labels: dict[str, str] = Field(default_factory=dict)
    max_concurrency: int = Field(default=1, ge=1)
    lease_ttl_seconds: int = Field(default=60, ge=5, le=3600)
    public_identity: str | None = None
    registered_at_iso: str
    last_heartbeat_at_iso: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutorHeartbeat(SchemaModel):
    kind: ClassVar[str] = "ExecutorHeartbeat"

    heartbeat_id: str
    agent_id: str
    occurred_at_iso: str
    status: AgentStatus
    active_task_ids: list[str] = Field(default_factory=list)
    available_capacity: int = Field(default=0, ge=0)
    capabilities: set[str] = Field(default_factory=set)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ExecutionTask(SchemaModel):
    kind: ClassVar[str] = "ExecutionTask"

    task_id: str
    organization_id: str
    workspace_id: str
    operation_id: str
    action_id: str
    environment_id: str
    action_type_id: str
    executor_id: str
    required_capabilities: set[str] = Field(default_factory=set)
    target_fingerprint: str | None = None
    status: TaskStatus = "queued"
    priority: int = Field(default=0, ge=-1000, le=1000)
    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=1, ge=1)
    not_before_iso: str | None = None
    deadline_iso: str | None = None
    assigned_agent_id: str | None = None
    idempotency_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str
    created_at_iso: str
    updated_at_iso: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_attempts(self) -> "ExecutionTask":
        if self.attempt > self.max_attempts:
            raise ValueError("task attempt cannot exceed max_attempts")
        return self


class TaskLease(SchemaModel):
    kind: ClassVar[str] = "TaskLease"

    lease_id: str
    task_id: str
    agent_id: str
    status: LeaseStatus = "active"
    acquired_at_iso: str
    expires_at_iso: str
    heartbeat_at_iso: str
    nonce: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DispatchDecision(SchemaModel):
    kind: ClassVar[str] = "DispatchDecision"

    decision_id: str
    task_id: str
    outcome: Literal["assigned", "queued", "blocked", "rejected"]
    agent_id: str | None = None
    candidate_agent_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    evaluated_at_iso: str
    metadata: dict[str, Any] = Field(default_factory=dict)
