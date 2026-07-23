from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from .base import SchemaModel


RegistryCategory = Literal[
    "canonical_type",
    "entity_type",
    "relationship_type",
    "invariant_family",
    "predicate_type",
    "disturbance_mechanism",
    "temporal_form",
    "mutation_type",
    "composition_operator",
    "scenario_family",
]


class RegistryEntry(SchemaModel):
    kind: ClassVar[str] = "RegistryEntry"

    registry_key: str
    category: RegistryCategory
    version: str = "1.0.0"
    title: str
    description: str = ""
    schema_ref: str | None = None
    capabilities: set[str] = Field(default_factory=set)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegistrySnapshot(SchemaModel):
    kind: ClassVar[str] = "RegistrySnapshot"

    entries: list[RegistryEntry]
    counts: dict[str, int]
