from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from .base import SchemaModel
from .predicate import Predicate
from .relationship import Relationship


class CompositionComponent(SchemaModel):
    kind: ClassVar[str] = "CompositionComponent"

    alias: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    family_id: str
    bindings: dict[str, Any] = Field(default_factory=dict)
    disturbance_id: str | None = None
    observation_profile_id: str | None = None
    start_at_seconds: int | None = Field(default=None, ge=0)
    duration_hint_seconds: int = Field(default=8, ge=1)
    activation_predicate: Predicate | None = None


class ScenarioComposition(SchemaModel):
    kind: ClassVar[str] = "ScenarioComposition"

    composition_id: str
    title: str
    operator: Literal[
        "concurrent",
        "sequential",
        "conditional",
        "masking",
        "recovery_interference",
    ]
    components: list[CompositionComponent] = Field(min_length=2)
    bridge_relationships: list[Relationship] = Field(default_factory=list)
    masked_aliases: set[str] = Field(default_factory=set)
    gap_seconds: int = Field(default=1, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_components(self) -> "ScenarioComposition":
        aliases = [component.alias for component in self.components]
        if len(set(aliases)) != len(aliases):
            raise ValueError("composition component aliases must be unique")
        unknown_masked = self.masked_aliases - set(aliases)
        if unknown_masked:
            raise ValueError(f"masked aliases are not components: {sorted(unknown_masked)}")
        if self.operator == "masking" and not self.masked_aliases:
            raise ValueError("masking compositions require at least one masked alias")
        if self.operator == "conditional":
            for component in self.components[1:]:
                if component.activation_predicate is None:
                    raise ValueError(
                        "conditional components after the first require activation_predicate"
                    )
        return self
