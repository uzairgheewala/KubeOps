from __future__ import annotations

from copy import deepcopy
from typing import Any


_MISSING = object()


def get_path(data: Any, path: str, default: Any = _MISSING) -> Any:
    current = data
    if not path:
        return current
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            if default is _MISSING:
                raise KeyError(path)
            return default
    return current


def set_path(data: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    result = deepcopy(data)
    current: dict[str, Any] = result
    parts = path.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = deepcopy(value)
    return result


def delete_path(data: dict[str, Any], path: str) -> dict[str, Any]:
    result = deepcopy(data)
    current: dict[str, Any] = result
    parts = path.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            return result
        current = child
    current.pop(parts[-1], None)
    return result


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
