from __future__ import annotations

from pathlib import Path

import yaml

from kubeops_core.models.planning import ExecutionPolicy
from kubeops_core.registry.base import TypedRegistry


class ExecutionPolicyRegistry:
    def __init__(self) -> None:
        self._items: TypedRegistry[ExecutionPolicy] = TypedRegistry("execution policy registry")
        self._sources: dict[str, str] = {}

    def register(
        self,
        policy: ExecutionPolicy,
        *,
        source: str = "memory",
        replace: bool = False,
    ) -> None:
        self._items.register(policy.policy_id, policy, replace=replace)
        self._sources[policy.policy_id] = source

    def get(self, policy_id: str) -> ExecutionPolicy:
        return self._items.get(policy_id)

    def values(self) -> list[ExecutionPolicy]:
        return self._items.values()

    def source(self, policy_id: str) -> str:
        return self._sources[policy_id]

    def load_directory(self, directory: str | Path) -> int:
        count = 0
        for path in sorted(Path(directory).glob("*.y*ml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            if payload:
                self.register(ExecutionPolicy.model_validate(payload), source=str(path))
                count += 1
        return count

    def __len__(self) -> int:
        return len(self._items)
