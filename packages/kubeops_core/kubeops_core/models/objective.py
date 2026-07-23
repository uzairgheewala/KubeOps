from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from .base import SchemaModel


class OperationalObjective(SchemaModel):
    """A goal against which world state and recovery success are evaluated."""

    kind: ClassVar[str] = "OperationalObjective"

    objective_id: str
    title: str
    objective_type: Literal[
        "establish",
        "maintain",
        "transition",
        "diagnose",
        "recover",
        "quiesce",
        "restore",
    ]
    description: str = ""
    required_invariant_ids: list[str] = Field(default_factory=list)
    protected_invariant_ids: list[str] = Field(default_factory=list)
    success_metadata: dict[str, Any] = Field(default_factory=dict)


class OperationalProfile(SchemaModel):
    """A reusable desired operational state composed from objectives and contracts."""

    kind: ClassVar[str] = "OperationalProfile"

    profile_id: str
    title: str
    environment_class: str = "simulation"
    objective_ids: list[str] = Field(default_factory=list)
    required_invariant_ids: list[str] = Field(default_factory=list)
    optional_invariant_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
