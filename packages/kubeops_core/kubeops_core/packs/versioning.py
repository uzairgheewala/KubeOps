from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "Version":
        match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", value.strip())
        if not match:
            raise ValueError(f"invalid semantic version {value!r}")
        return cls(*(int(item or 0) for item in match.groups()))


def satisfies(version: str, constraint: str | None) -> bool:
    if not constraint or constraint.strip() in {"", "*"}:
        return True
    parsed = Version.parse(version)
    for clause in constraint.split(","):
        clause = clause.strip()
        if not clause:
            continue
        match = re.match(r"^(>=|<=|==|!=|>|<|~=)?\s*(.+)$", clause)
        if not match:
            return False
        operator, raw = match.groups()
        expected = Version.parse(raw)
        operator = operator or "=="
        if operator == ">=" and not parsed >= expected:
            return False
        if operator == "<=" and not parsed <= expected:
            return False
        if operator == ">" and not parsed > expected:
            return False
        if operator == "<" and not parsed < expected:
            return False
        if operator == "==" and not parsed == expected:
            return False
        if operator == "!=" and not parsed != expected:
            return False
        if operator == "~=":
            upper = Version(expected.major + 1, 0, 0) if expected.minor == 0 else Version(expected.major, expected.minor + 1, 0)
            if not (parsed >= expected and parsed < upper):
                return False
    return True
