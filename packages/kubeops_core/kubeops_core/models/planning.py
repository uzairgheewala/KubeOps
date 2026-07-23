from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from .base import SchemaModel
from .predicate import Predicate


RiskClass = Literal["R0", "R1", "R2", "R3", "R4", "R5"]


class RiskAssessment(SchemaModel):
    kind: ClassVar[str] = "RiskAssessment"

    risk_class: RiskClass = "R0"
    blast_radius: str = "none"
    availability_risk: str = "none"
    data_risk: str = "none"
    security_risk: str = "none"
    reversible: bool = True
    idempotent: bool = True
    rationale: list[str] = Field(default_factory=list)


class ActionTypeDefinition(SchemaModel):
    """Stable semantic action contract; concrete executors arrive in later releases."""

    kind: ClassVar[str] = "ActionTypeDefinition"

    action_type_id: str
    title: str
    description: str = ""
    parameter_schema: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[Predicate] = Field(default_factory=list)
    expected_effects: list[str] = Field(default_factory=list)
    possible_side_effects: list[str] = Field(default_factory=list)
    required_capabilities: set[str] = Field(default_factory=set)
    default_risk: RiskAssessment = Field(default_factory=RiskAssessment)
    completion_condition_ids: list[str] = Field(default_factory=list)
    rollback_action_type_id: str | None = None


class ActionInstance(SchemaModel):
    kind: ClassVar[str] = "ActionInstance"

    action_id: str
    action_type_id: str
    target_ids: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    depends_on_action_ids: list[str] = Field(default_factory=list)
    risk: RiskAssessment = Field(default_factory=RiskAssessment)
    status: Literal[
        "proposed",
        "authorized",
        "running",
        "completed",
        "failed",
        "skipped",
        "rolled_back",
    ] = "proposed"
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionPolicy(SchemaModel):
    kind: ClassVar[str] = "ExecutionPolicy"

    policy_id: str
    title: str
    environment_classes: set[str] = Field(default_factory=set)
    allowed_risk_classes: set[RiskClass] = Field(default_factory=lambda: {"R0"})
    allowed_action_type_ids: set[str] = Field(default_factory=set)
    denied_action_type_ids: set[str] = Field(default_factory=set)
    required_approvals_by_risk: dict[RiskClass, int] = Field(default_factory=dict)
    maximum_concurrent_actions: int = Field(default=1, ge=1)
    require_checkpoint_for_risk: set[RiskClass] = Field(default_factory=set)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyDecision(SchemaModel):
    kind: ClassVar[str] = "PolicyDecision"

    decision_id: str
    policy_id: str
    action_id: str
    outcome: Literal["allow", "deny", "approval_required"]
    reasons: list[str] = Field(default_factory=list)
    required_approval_count: int = Field(default=0, ge=0)


class RecoveryPlan(SchemaModel):
    kind: ClassVar[str] = "RecoveryPlan"

    plan_id: str
    incident_id: str | None = None
    objective_id: str
    target_invariant_ids: list[str] = Field(default_factory=list)
    protected_invariant_ids: list[str] = Field(default_factory=list)
    actions: list[ActionInstance] = Field(default_factory=list)
    mode: Literal["guidance", "dry_run", "guarded_execution"] = "guidance"
    policy_id: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    unsupported_assumptions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_action_graph(self) -> "RecoveryPlan":
        action_ids = {action.action_id for action in self.actions}
        if len(action_ids) != len(self.actions):
            raise ValueError("recovery-plan action ids must be unique")
        for action in self.actions:
            unknown = set(action.depends_on_action_ids) - action_ids
            if unknown:
                raise ValueError(
                    f"action {action.action_id} depends on unknown actions: {sorted(unknown)}"
                )
            if action.action_id in action.depends_on_action_ids:
                raise ValueError(f"action {action.action_id} cannot depend on itself")
        self._assert_acyclic()
        return self

    def _assert_acyclic(self) -> None:
        dependencies = {
            action.action_id: set(action.depends_on_action_ids) for action in self.actions
        }
        ready = [action_id for action_id, deps in dependencies.items() if not deps]
        visited: set[str] = set()
        while ready:
            action_id = ready.pop()
            if action_id in visited:
                continue
            visited.add(action_id)
            for candidate, deps in dependencies.items():
                deps.discard(action_id)
                if not deps and candidate not in visited:
                    ready.append(candidate)
        if len(visited) != len(dependencies):
            raise ValueError("recovery-plan action graph must be acyclic")
