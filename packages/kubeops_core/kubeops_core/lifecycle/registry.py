from __future__ import annotations

from pathlib import Path

import yaml

from kubeops_core.models.lifecycle import LifecycleProfile
from kubeops_core.registry.base import TypedRegistry


class LifecycleProfileRegistry:
    def __init__(self) -> None:
        self._items: TypedRegistry[LifecycleProfile] = TypedRegistry("lifecycle profile registry")
        self._sources: dict[str, str] = {}

    def register(
        self,
        profile: LifecycleProfile,
        *,
        source: str = "memory",
        replace: bool = False,
    ) -> None:
        self._items.register(profile.profile_id, profile, replace=replace)
        self._sources[profile.profile_id] = source

    def get(self, profile_id: str) -> LifecycleProfile:
        return self._items.get(profile_id)

    def values(self) -> list[LifecycleProfile]:
        return self._items.values()

    def source(self, profile_id: str) -> str:
        return self._sources[profile_id]

    def load_directory(self, directory: str | Path) -> int:
        count = 0
        for path in sorted(Path(directory).glob("*.y*ml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            if payload:
                self.register(LifecycleProfile.model_validate(payload), source=str(path))
                count += 1
        return count

    def __len__(self) -> int:
        return len(self._items)
