from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from kubeops_core.models.environment import AccessValidationResult, EnvironmentDefinition


@dataclass(frozen=True)
class RawCollection:
    source_type: str
    source_fingerprint: str
    resources: dict[str, list[dict[str, Any]]]
    issues: list[dict[str, Any]] = field(default_factory=list)
    permission_gaps: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class DiscoverySource(Protocol):
    source_id: str

    def validate(self, environment: EnvironmentDefinition, method_id: str | None = None) -> AccessValidationResult:
        ...

    def collect(
        self,
        environment: EnvironmentDefinition,
        method_id: str | None = None,
        resource_types: list[str] | None = None,
    ) -> RawCollection:
        ...
