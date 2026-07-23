from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from .base import SchemaModel

FleetStatus = Literal["healthy", "degraded", "unavailable", "recovering", "unknown", "quiesced"]


class FleetMember(SchemaModel):
    kind: ClassVar[str] = "FleetMember"

    environment_id: str
    required_profile_ids: list[str] = Field(default_factory=list)
    criticality: str = "standard"
    failure_domain: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class FleetDependency(SchemaModel):
    kind: ClassVar[str] = "FleetDependency"

    dependency_id: str
    source_environment_id: str
    target_environment_id: str
    relationship_type: str = "requires_for_service"
    required_profile_id: str | None = None
    maximum_unavailability_seconds: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_self_dependency(self) -> "FleetDependency":
        if self.source_environment_id == self.target_environment_id:
            raise ValueError("fleet dependencies must connect distinct environments")
        return self


class FleetDefinition(SchemaModel):
    kind: ClassVar[str] = "FleetDefinition"

    fleet_id: str
    organization_id: str
    workspace_id: str
    name: str
    members: list[FleetMember] = Field(default_factory=list)
    dependencies: list[FleetDependency] = Field(default_factory=list)
    max_parallel_operations: int = Field(default=1, ge=1)
    active: bool = True
    labels: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_members(self) -> "FleetDefinition":
        ids = [item.environment_id for item in self.members]
        if len(ids) != len(set(ids)):
            raise ValueError("fleet member environment IDs must be unique")
        member_ids = set(ids)
        for dependency in self.dependencies:
            if dependency.source_environment_id not in member_ids or dependency.target_environment_id not in member_ids:
                raise ValueError("fleet dependency must reference fleet members")
        return self


class FleetEnvironmentStatus(SchemaModel):
    kind: ClassVar[str] = "FleetEnvironmentStatus"

    environment_id: str
    status: FleetStatus
    profile_statuses: dict[str, str] = Field(default_factory=dict)
    active_incident_ids: list[str] = Field(default_factory=list)
    active_operation_ids: list[str] = Field(default_factory=list)
    source_snapshot_id: str | None = None
    observed_at_iso: str | None = None
    reasons: list[str] = Field(default_factory=list)


class CommonCauseFinding(SchemaModel):
    kind: ClassVar[str] = "CommonCauseFinding"

    finding_id: str
    family_id: str
    title: str
    environment_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    shared_factors: dict[str, str] = Field(default_factory=dict)
    incident_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FleetAssessment(SchemaModel):
    kind: ClassVar[str] = "FleetAssessment"

    assessment_id: str
    fleet_id: str
    status: FleetStatus
    generated_at_iso: str
    environments: list[FleetEnvironmentStatus]
    common_causes: list[CommonCauseFinding] = Field(default_factory=list)
    dependency_violations: list[str] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FleetOperationWave(SchemaModel):
    kind: ClassVar[str] = "FleetOperationWave"

    wave_index: int = Field(ge=0)
    environment_ids: list[str]
    blocked_by_environment_ids: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)


class FleetOperationPlan(SchemaModel):
    kind: ClassVar[str] = "FleetOperationPlan"

    plan_id: str
    fleet_id: str
    operation_type: Literal["startup", "shutdown", "maintenance", "recovery", "verification"]
    created_at_iso: str
    waves: list[FleetOperationWave]
    max_parallel_operations: int = Field(ge=1)
    protected_environment_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
