from __future__ import annotations

from typing import Any, ClassVar

from pydantic import Field

from .base import SchemaModel


class Relationship(SchemaModel):
    kind: ClassVar[str] = "Relationship"

    relationship_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    relationship_type: str = Field(min_length=1)
    contract: dict[str, Any] = Field(default_factory=dict)
    propagation: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: str = "scenario"
    extensions: dict[str, Any] = Field(default_factory=dict)
