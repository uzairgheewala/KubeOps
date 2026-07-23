from __future__ import annotations

from collections.abc import Iterable
from typing import Generic, TypeVar

T = TypeVar("T")


class RegistryError(ValueError):
    pass


class TypedRegistry(Generic[T]):
    """Deterministic registry with explicit duplicate rejection."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._items: dict[str, T] = {}

    def register(self, key: str, item: T, *, replace: bool = False) -> None:
        if key in self._items and not replace:
            raise RegistryError(f"{self.name} already contains {key}")
        self._items[key] = item

    def get(self, key: str) -> T:
        try:
            return self._items[key]
        except KeyError as exc:
            raise RegistryError(f"{self.name} does not contain {key}") from exc

    def maybe_get(self, key: str) -> T | None:
        return self._items.get(key)

    def keys(self) -> list[str]:
        return sorted(self._items)

    def values(self) -> list[T]:
        return [self._items[key] for key in self.keys()]

    def items(self) -> list[tuple[str, T]]:
        return [(key, self._items[key]) for key in self.keys()]

    def extend(self, items: Iterable[tuple[str, T]], *, replace: bool = False) -> None:
        for key, item in items:
            self.register(key, item, replace=replace)

    def __len__(self) -> int:
        return len(self._items)
