from __future__ import annotations

from collections import Counter

from kubeops_core.models.registry import RegistryEntry, RegistrySnapshot

from .base import TypedRegistry


class RegistryCatalog:
    """Unified introspection catalog for every Release 0.1 extension surface."""

    def __init__(self) -> None:
        self._entries: TypedRegistry[RegistryEntry] = TypedRegistry("core registry catalog")

    def register(self, entry: RegistryEntry, *, replace: bool = False) -> None:
        identity = f"{entry.category}:{entry.registry_key}"
        self._entries.register(identity, entry, replace=replace)

    def entries(self, category: str | None = None) -> list[RegistryEntry]:
        values = self._entries.values()
        if category is None:
            return values
        return [entry for entry in values if entry.category == category]

    def snapshot(self) -> RegistrySnapshot:
        entries = self.entries()
        counts = Counter(entry.category for entry in entries)
        return RegistrySnapshot(entries=entries, counts=dict(sorted(counts.items())))
