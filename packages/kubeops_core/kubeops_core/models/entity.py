from __future__ import annotations

from typing import Any, ClassVar

from pydantic import Field

from .base import SchemaModel
from .enums import OperationalPlane


class EntityRef(SchemaModel):
    kind: ClassVar[str] = "EntityRef"
    entity_id: str = Field(min_length=1)


class OperationalEntity(SchemaModel):
    kind: ClassVar[str] = "OperationalEntity"

    entity_id: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    entity_type_lineage: set[str] = Field(default_factory=set)
    name: str = Field(min_length=1)
    plane: OperationalPlane
    namespace: str | None = None
    provider: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    desired_state: dict[str, Any] = Field(default_factory=dict)
    observed_state: dict[str, Any] = Field(default_factory=dict)
    capabilities: set[str] = Field(default_factory=set)
    extensions: dict[str, Any] = Field(default_factory=dict)
