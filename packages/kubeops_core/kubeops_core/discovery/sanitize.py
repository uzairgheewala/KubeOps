from __future__ import annotations

from copy import deepcopy
from typing import Any


SENSITIVE_KEYS = {
    "data",
    "stringData",
    "token",
    "password",
    "clientSecret",
    "client_secret",
    "privateKey",
    "private_key",
    "certificate-authority-data",
    "client-certificate-data",
    "client-key-data",
}


def sanitize_resource(resource: dict[str, Any]) -> dict[str, Any]:
    """Remove secret values while preserving structure needed for diagnosis."""

    result = deepcopy(resource)
    kind = str(result.get("kind", ""))
    if kind == "Secret":
        data = result.pop("data", None)
        string_data = result.pop("stringData", None)
        result["redaction"] = {
            "data_keys": sorted(data.keys()) if isinstance(data, dict) else [],
            "string_data_keys": sorted(string_data.keys()) if isinstance(string_data, dict) else [],
            "values_removed": True,
        }

    def walk(value: Any, parent_key: str | None = None) -> Any:
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for key, child in value.items():
                if key in SENSITIVE_KEYS and not (kind == "Secret" and key == "data"):
                    cleaned[key] = "<redacted>"
                else:
                    cleaned[key] = walk(child, key)
            return cleaned
        if isinstance(value, list):
            return [walk(item, parent_key) for item in value]
        return value

    return walk(result)
