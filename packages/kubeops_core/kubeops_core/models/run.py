from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from .base import SchemaModel
from .enums import RunStatus
from .invariant import InvariantEvaluation
from .observation import Observation


class TimelineEvent(SchemaModel):
    kind: ClassVar[str] = "TimelineEvent"

    sequence: int = Field(ge=0)
    at_seconds: int = Field(ge=0)
    event_type: str
    title: str
    entity_id: str | None = None
    rule_id: str | None = None
    mutation_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class WorldSnapshot(SchemaModel):
    kind: ClassVar[str] = "WorldSnapshot"

    sequence: int = Field(ge=0)
    at_seconds: int = Field(ge=0)
    trigger_event_sequence: int | None = None
    truth_state: dict[str, dict[str, Any]]
    observed_state: dict[str, dict[str, Any]]
    invariant_evaluations: list[InvariantEvaluation]


class SimulationRun(SchemaModel):
    kind: ClassVar[str] = "SimulationRun"

    run_id: str
    scenario_id: str
    family_id: str
    status: RunStatus
    started_at_iso: str
    completed_at_iso: str | None = None
    seed: int = 0
    timeline: list[TimelineEvent] = Field(default_factory=list)
    snapshots: list[WorldSnapshot] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    final_summary: dict[str, Any] = Field(default_factory=dict)


class RunArtifact(SchemaModel):
    kind: ClassVar[str] = "RunArtifact"

    artifact_id: str
    run_id: str
    artifact_type: Literal[
        "scenario_instance",
        "timeline",
        "snapshot",
        "observation_set",
        "run_manifest",
    ]
    payload_hash: str
    media_type: str = "application/json"
    payload: dict[str, Any] | list[Any]
    derived_from: list[str] = Field(default_factory=list)
