from __future__ import annotations

from pathlib import Path

import yaml

from kubeops_core.models.scenario import ScenarioFamily

from .base import TypedRegistry


class ScenarioFamilyRegistry(TypedRegistry[ScenarioFamily]):
    def __init__(self) -> None:
        super().__init__("scenario family registry")

    def register_family(self, family: ScenarioFamily, *, replace: bool = False) -> None:
        self.register(family.family_id, family, replace=replace)

    def load_yaml_file(self, path: str | Path, *, replace: bool = False) -> ScenarioFamily:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        family = ScenarioFamily.model_validate(payload)
        self.register_family(family, replace=replace)
        return family

    def load_directory(self, path: str | Path, *, replace: bool = False) -> list[ScenarioFamily]:
        directory = Path(path)
        loaded: list[ScenarioFamily] = []
        for file_path in sorted(directory.rglob("*.yaml")):
            loaded.append(self.load_yaml_file(file_path, replace=replace))
        return loaded

    def lineage(self, family_id: str) -> list[ScenarioFamily]:
        lineage: list[ScenarioFamily] = []
        current = self.get(family_id)
        seen: set[str] = set()
        while current:
            if current.family_id in seen:
                raise ValueError(f"scenario-family inheritance cycle at {current.family_id}")
            seen.add(current.family_id)
            lineage.append(current)
            if current.parent_family_id is None:
                break
            current = self.get(current.parent_family_id)
        return list(reversed(lineage))
