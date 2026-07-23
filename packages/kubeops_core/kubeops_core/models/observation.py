from __future__ import annotations

from typing import Any, ClassVar

from pydantic import Field

from .base import SchemaModel
from .enums import ObservationProfileKind


class ObservationProfile(SchemaModel):
    kind: ClassVar[str] = "ObservationProfile"

    profile_id: str
    title: str
    profile_kind: ObservationProfileKind = ObservationProfileKind.FULL
    hidden_entity_ids: set[str] = Field(default_factory=set)
    hidden_paths: dict[str, set[str]] = Field(default_factory=dict)
    lag_seconds: dict[str, int] = Field(default_factory=dict)
    contradictory_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class Observation(SchemaModel):
    kind: ClassVar[str] = "Observation"

    observation_id: str
    entity_id: str
    observed_at: int = Field(default=0, ge=0)
    observed_at_iso: str | None = None
    state: dict[str, Any]
    source: str = "simulator"
    authority: str = "authoritative"
    freshness_seconds: int = 0
    profile_id: str = "full"
