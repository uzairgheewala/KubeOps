from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from .base import SchemaModel
from .predicate import Predicate


class StateMutation(SchemaModel):
    kind: ClassVar[str] = "StateMutation"

    mutation_type: Literal["set_state", "delete_entity", "create_entity"] = "set_state"
    entity_id: str
    path: str | None = None
    value: Any = None
    entity_payload: dict[str, Any] | None = None


class ScheduledMutation(SchemaModel):
    kind: ClassVar[str] = "ScheduledMutation"

    mutation_id: str
    at_seconds: int = Field(ge=0)
    description: str
    mutation: StateMutation


class TransitionRule(SchemaModel):
    kind: ClassVar[str] = "TransitionRule"

    rule_id: str
    title: str
    conditions: list[Predicate] = Field(default_factory=list)
    effects: list[StateMutation] = Field(default_factory=list)
    delay_seconds: int = Field(default=0, ge=0)
    fire_once: bool = False
