from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from .action import ScheduledMutation, TransitionRule
from .base import SchemaModel
from .entity import OperationalEntity
from .enums import DisturbanceMechanism, TemporalForm
from .invariant import InvariantDefinition
from .observation import ObservationProfile
from .relationship import Relationship


class ParameterSpec(SchemaModel):
    kind: ClassVar[str] = "ParameterSpec"

    name: str
    title: str
    parameter_type: Literal["string", "integer", "boolean", "enum"]
    description: str = ""
    required: bool = True
    default: Any = None
    options: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_options(self) -> "ParameterSpec":
        if self.parameter_type == "enum" and not self.options:
            raise ValueError("enum parameters require options")
        return self


class ConstraintSpec(SchemaModel):
    kind: ClassVar[str] = "ConstraintSpec"

    constraint_type: Literal["required", "not_equal", "one_of"]
    parameters: list[str]
    values: list[Any] = Field(default_factory=list)
    message: str


class FamilySignature(SchemaModel):
    kind: ClassVar[str] = "FamilySignature"

    invariant_families: list[str]
    disturbance_mechanisms: list[DisturbanceMechanism]
    temporal_forms: list[TemporalForm]
    topology_patterns: list[str] = Field(default_factory=list)
    observation_profiles: list[str] = Field(default_factory=list)
    recovery_strategy_classes: list[str] = Field(default_factory=list)
    coverage_labels: list[str] = Field(default_factory=list)


class DisturbanceDefinition(SchemaModel):
    kind: ClassVar[str] = "DisturbanceDefinition"

    disturbance_id: str
    title: str
    mechanism: DisturbanceMechanism
    temporal_form: TemporalForm
    mutations: list[ScheduledMutation]


class ScenarioBlueprint(SchemaModel):
    kind: ClassVar[str] = "ScenarioBlueprint"

    entities: list[dict[str, Any]]
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    invariants: list[dict[str, Any]] = Field(default_factory=list)
    transition_rules: list[dict[str, Any]] = Field(default_factory=list)
    observation_profiles: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioFamily(SchemaModel):
    kind: ClassVar[str] = "ScenarioFamily"

    family_id: str
    version: str
    title: str
    description: str
    parent_family_id: str | None = None
    abstract: bool = False
    parameters: list[ParameterSpec] = Field(default_factory=list)
    constraints: list[ConstraintSpec] = Field(default_factory=list)
    signature: FamilySignature
    blueprint: ScenarioBlueprint
    disturbances: list[dict[str, Any]]
    default_disturbance_id: str
    default_observation_profile_id: str = "full"
    tags: list[str] = Field(default_factory=list)


class ScenarioInstance(SchemaModel):
    kind: ClassVar[str] = "ScenarioInstance"

    scenario_id: str
    family_id: str
    family_version: str
    title: str
    description: str
    bindings: dict[str, Any]
    entities: list[OperationalEntity]
    relationships: list[Relationship]
    invariants: list[InvariantDefinition]
    transition_rules: list[TransitionRule]
    disturbance: DisturbanceDefinition
    observation_profile: ObservationProfile
    max_time_seconds: int = Field(default=20, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "ScenarioInstance":
        entity_ids = {entity.entity_id for entity in self.entities}
        if len(entity_ids) != len(self.entities):
            raise ValueError("entity ids must be unique")
        for relationship in self.relationships:
            if relationship.source_id not in entity_ids:
                raise ValueError(f"unknown relationship source {relationship.source_id}")
            if relationship.target_id not in entity_ids:
                raise ValueError(f"unknown relationship target {relationship.target_id}")
        for invariant in self.invariants:
            if invariant.subject_id not in entity_ids:
                raise ValueError(f"unknown invariant subject {invariant.subject_id}")
        return self
