from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from .base import SchemaModel
from .enums import HealthStatus


AccessMethodType = Literal["kubectl", "kubeconfig", "fixture"]
EnvironmentClass = Literal["simulation", "development", "staging", "production"]


class AccessMethodDefinition(SchemaModel):
    """A read-oriented route by which KubeOps can inspect an environment."""

    kind: ClassVar[str] = "AccessMethodDefinition"

    method_id: str = Field(min_length=1)
    method_type: AccessMethodType
    title: str = ""
    context_name: str | None = None
    kubeconfig_path: str | None = None
    fixture_path: str | None = None
    command: str = "kubectl"
    read_only: bool = True
    timeout_seconds: int = Field(default=30, ge=1, le=600)
    credential_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_method(self) -> "AccessMethodDefinition":
        if self.method_type == "fixture" and not self.fixture_path:
            raise ValueError("fixture access methods require fixture_path")
        return self


class EnvironmentDefinition(SchemaModel):
    kind: ClassVar[str] = "EnvironmentDefinition"

    environment_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    environment_class: EnvironmentClass = "development"
    provider: str = "generic"
    cluster_provider: str = "generic-kubernetes"
    host_provider: str | None = None
    criticality: str = "standard"
    access_methods: list[AccessMethodDefinition] = Field(min_length=1)
    default_access_method_id: str | None = None
    operational_profile_ids: list[str] = Field(default_factory=list)
    installed_pack_ids: list[str] = Field(default_factory=lambda: ["generic-kubernetes"])
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_access_methods(self) -> "EnvironmentDefinition":
        ids = [method.method_id for method in self.access_methods]
        if len(ids) != len(set(ids)):
            raise ValueError("access method IDs must be unique")
        if self.default_access_method_id and self.default_access_method_id not in ids:
            raise ValueError("default_access_method_id must reference an access method")
        return self

    def access_method(self, method_id: str | None = None) -> AccessMethodDefinition:
        requested = method_id or self.default_access_method_id
        if requested is None and self.access_methods:
            return self.access_methods[0]
        for method in self.access_methods:
            if method.method_id == requested:
                return method
        raise KeyError(f"unknown access method {requested!r}")


class AccessCheck(SchemaModel):
    kind: ClassVar[str] = "AccessCheck"

    check_id: str
    title: str
    status: HealthStatus
    explanation: str
    authority: str = "collector"
    details: dict[str, Any] = Field(default_factory=dict)


class PermissionGap(SchemaModel):
    kind: ClassVar[str] = "PermissionGap"

    resource: str
    verb: str = "list"
    scope: str = "cluster"
    reason: str = "permission denied"
    required_for: list[str] = Field(default_factory=list)


class AccessValidationResult(SchemaModel):
    kind: ClassVar[str] = "AccessValidationResult"

    validation_id: str
    environment_id: str
    access_method_id: str
    checked_at_iso: str
    status: HealthStatus
    target_fingerprint: str
    current_context: str | None = None
    cluster_server: str | None = None
    cluster_version: str | None = None
    capabilities: set[str] = Field(default_factory=set)
    checks: list[AccessCheck] = Field(default_factory=list)
    permission_gaps: list[PermissionGap] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
