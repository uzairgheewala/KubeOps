from __future__ import annotations

from typing import Any, ClassVar

from pydantic import Field

from .base import SchemaModel


class OperationalArtifact(SchemaModel):
    kind: ClassVar[str] = "OperationalArtifact"

    artifact_id: str
    scope_type: str
    scope_id: str
    artifact_type: str
    payload_hash: str
    media_type: str = "application/json"
    payload: dict[str, Any] | list[Any]
    derived_from: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
