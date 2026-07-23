from __future__ import annotations

from pathlib import Path

import yaml

from kubeops_core.models.health import OperationalProfileSpec


class OperationalProfileRegistry:
    def __init__(self) -> None:
        self._profiles: dict[str, OperationalProfileSpec] = {}
        self._sources: dict[str, str] = {}

    def register(self, profile: OperationalProfileSpec, source: str = "memory") -> None:
        existing = self._profiles.get(profile.profile_id)
        if existing and existing.content_hash != profile.content_hash:
            raise ValueError(f"operational profile {profile.profile_id} already registered with different content")
        self._profiles[profile.profile_id] = profile
        self._sources[profile.profile_id] = source

    def load_pack_runtime(self, pack_runtime) -> int:
        count = 0
        for profile in pack_runtime.operational_profiles():
            self.register(profile, source=f"pack:{profile.metadata.get('pack_id', 'unknown')}")
            count += 1
        return count

    def load_directory(self, directory: str | Path) -> int:
        count = 0
        for path in sorted(Path(directory).glob("*.yaml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.register(OperationalProfileSpec.model_validate(payload), str(path))
            count += 1
        return count

    def get(self, profile_id: str) -> OperationalProfileSpec:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise KeyError(f"unknown operational profile {profile_id!r}") from exc

    def values(self) -> list[OperationalProfileSpec]:
        return [self._profiles[key] for key in sorted(self._profiles)]

    def source(self, profile_id: str) -> str:
        return self._sources[profile_id]

    def __len__(self) -> int:
        return len(self._profiles)
