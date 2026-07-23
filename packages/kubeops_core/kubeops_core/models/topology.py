from __future__ import annotations

from typing import Any, ClassVar

from pydantic import Field

from .base import SchemaModel
from .entity import OperationalEntity
from .relationship import Relationship


class TopologyGraph(SchemaModel):
    kind: ClassVar[str] = "TopologyGraph"

    graph_id: str
    environment_id: str
    snapshot_id: str
    generated_at_iso: str
    entities: list[OperationalEntity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    layers: dict[str, list[str]] = Field(default_factory=dict)
    statistics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
