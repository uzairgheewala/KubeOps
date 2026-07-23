from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from .base import SchemaModel
from .enums import HealthStatus, InvariantFamily, Severity
from .predicate import Predicate


class TemporalRequirement(SchemaModel):
    kind: ClassVar[str] = "TemporalRequirement"

    operator: Literal["immediate", "eventually", "stable_for"] = "immediate"
    within_seconds: int | None = Field(default=None, ge=0)
    stable_for_seconds: int | None = Field(default=None, ge=0)


class InvariantDefinition(SchemaModel):
    kind: ClassVar[str] = "InvariantDefinition"

    invariant_id: str
    title: str
    family: InvariantFamily
    subject_id: str
    predicate: Predicate
    severity: Severity = Severity.ERROR
    temporal: TemporalRequirement = Field(default_factory=TemporalRequirement)
    description: str = ""
    affected_objectives: list[str] = Field(default_factory=list)


class InvariantEvaluation(SchemaModel):
    kind: ClassVar[str] = "InvariantEvaluation"

    invariant_id: str
    status: HealthStatus
    evaluated_at: int = Field(ge=0)
    actual_value: object | None = None
    expected: object | None = None
    explanation: str
    evidence_entity_ids: list[str] = Field(default_factory=list)
