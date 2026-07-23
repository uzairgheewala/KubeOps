from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from kubeops_core.models.entity import OperationalEntity
from kubeops_core.util import set_path


@dataclass
class MutableWorld:
    entities: dict[str, dict[str, Any]]

    @classmethod
    def from_entities(cls, entities: list[OperationalEntity]) -> "MutableWorld":
        return cls(
            entities={
                entity.entity_id: entity.model_dump(mode="python", exclude={"schema_version"})
                for entity in entities
            }
        )

    def copy_state(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self.entities)

    def set_state(self, entity_id: str, path: str, value: Any) -> tuple[Any, Any]:
        if entity_id not in self.entities:
            raise KeyError(f"unknown entity {entity_id}")
        before = deepcopy(self.entities[entity_id])
        self.entities[entity_id] = set_path(self.entities[entity_id], path, value)
        return before, deepcopy(self.entities[entity_id])

    def delete_entity(self, entity_id: str) -> dict[str, Any] | None:
        return self.entities.pop(entity_id, None)

    def create_entity(self, payload: dict[str, Any]) -> None:
        entity = OperationalEntity.model_validate(payload)
        if entity.entity_id in self.entities:
            raise ValueError(f"entity {entity.entity_id} already exists")
        self.entities[entity.entity_id] = entity.model_dump(mode="python", exclude={"schema_version"})
