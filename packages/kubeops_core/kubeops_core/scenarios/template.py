from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

_FULL = re.compile(r"^\$\{([A-Za-z0-9_.-]+)\}$")
_EMBEDDED = re.compile(r"\$\{([A-Za-z0-9_.-]+)\}")


class TemplateResolutionError(ValueError):
    pass


def resolve_template(value: Any, bindings: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: resolve_template(child, bindings) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve_template(child, bindings) for child in value]
    if isinstance(value, tuple):
        return tuple(resolve_template(child, bindings) for child in value)
    if not isinstance(value, str):
        return deepcopy(value)

    full_match = _FULL.match(value)
    if full_match:
        key = full_match.group(1)
        if key not in bindings:
            raise TemplateResolutionError(f"missing template binding {key}")
        return deepcopy(bindings[key])

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in bindings:
            raise TemplateResolutionError(f"missing template binding {key}")
        return str(bindings[key])

    return _EMBEDDED.sub(replace, value)
