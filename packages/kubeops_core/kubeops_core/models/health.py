from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from .base import SchemaModel
from .enums import HealthStatus, InvariantFamily, Severity
from .invariant import InvariantDefinition, InvariantEvaluation, TemporalRequirement


class EntitySelector(SchemaModel):
    kind: ClassVar[str] = "EntitySelector"

    entity_types: set[str] = Field(default_factory=set)
    planes: set[str] = Field(default_factory=set)
    namespaces: set[str] = Field(default_factory=set)
    names: set[str] = Field(default_factory=set)
    labels: dict[str, str] = Field(default_factory=dict)
    exclude_namespaces: set[str] = Field(default_factory=set)
    include_cluster_scoped: bool = True


class InvariantTemplate(SchemaModel):
    kind: ClassVar[str] = "InvariantTemplate"

    template_id: str
    title: str
    description: str = ""
    family: InvariantFamily
    selector: EntitySelector = Field(default_factory=EntitySelector)
    check_type: Literal[
        "entity_observed",
        "field_equals",
        "field_gte",
        "fields_equal",
        "node_ready",
        "pod_ready",
        "workload_available",
        "controller_progress",
        "service_has_ready_endpoints",
        "pvc_bound",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)
    severity: Severity = Severity.ERROR
    temporal: TemporalRequirement = Field(default_factory=TemporalRequirement)
    required: bool = True
    affected_objectives: list[str] = Field(default_factory=list)


class OperationalProfileSpec(SchemaModel):
    kind: ClassVar[str] = "OperationalProfileSpec"

    profile_id: str
    version: str = "1.0.0"
    title: str
    description: str = ""
    environment_classes: set[str] = Field(default_factory=set)
    objective_ids: list[str] = Field(default_factory=list)
    invariant_templates: list[InvariantTemplate] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompiledOperationalProfile(SchemaModel):
    kind: ClassVar[str] = "CompiledOperationalProfile"

    profile_id: str
    version: str
    environment_id: str
    snapshot_id: str
    compiled_at_iso: str
    invariants: list[InvariantDefinition] = Field(default_factory=list)
    required_invariant_ids: list[str] = Field(default_factory=list)
    optional_invariant_ids: list[str] = Field(default_factory=list)
    unmatched_templates: list[str] = Field(default_factory=list)


class OperationalProfileAssessment(SchemaModel):
    kind: ClassVar[str] = "OperationalProfileAssessment"

    assessment_id: str
    profile_id: str
    profile_version: str
    environment_id: str
    snapshot_id: str
    evaluated_at_iso: str
    status: HealthStatus
    evaluations: list[InvariantEvaluation] = Field(default_factory=list)
    required_invariant_ids: list[str] = Field(default_factory=list)
    optional_invariant_ids: list[str] = Field(default_factory=list)
    violated_invariant_ids: list[str] = Field(default_factory=list)
    unknown_invariant_ids: list[str] = Field(default_factory=list)
    pending_invariant_ids: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    objective_impact: dict[str, list[str]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
