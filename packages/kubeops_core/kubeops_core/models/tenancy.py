from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from .base import SchemaModel

RoleName = Literal["viewer", "operator", "approver", "auditor", "admin"]
ScopeType = Literal["organization", "workspace", "fleet", "environment", "operation", "global"]
AuthorizationOutcome = Literal["allow", "deny", "challenge"]


class OrganizationDefinition(SchemaModel):
    kind: ClassVar[str] = "OrganizationDefinition"

    organization_id: str
    name: str
    slug: str
    active: bool = True
    labels: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceDefinition(SchemaModel):
    kind: ClassVar[str] = "WorkspaceDefinition"

    workspace_id: str
    organization_id: str
    name: str
    slug: str
    active: bool = True
    labels: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoleGrant(SchemaModel):
    kind: ClassVar[str] = "RoleGrant"

    grant_id: str
    principal_id: str
    role: RoleName
    scope_type: ScopeType
    scope_id: str
    capabilities: set[str] = Field(default_factory=set)
    environment_classes: set[str] = Field(default_factory=set)
    granted_by: str | None = None
    granted_at_iso: str
    expires_at_iso: str | None = None
    active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthorizationRequest(SchemaModel):
    kind: ClassVar[str] = "AuthorizationRequest"

    request_id: str
    principal_id: str
    action: str
    scope_type: ScopeType
    scope_id: str
    required_roles: set[RoleName] = Field(default_factory=set)
    required_capabilities: set[str] = Field(default_factory=set)
    environment_class: str | None = None
    resource_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class AuthorizationDecision(SchemaModel):
    kind: ClassVar[str] = "AuthorizationDecision"

    decision_id: str
    request_id: str
    principal_id: str
    outcome: AuthorizationOutcome
    matched_grant_ids: list[str] = Field(default_factory=list)
    effective_roles: set[RoleName] = Field(default_factory=set)
    effective_capabilities: set[str] = Field(default_factory=set)
    reasons: list[str] = Field(default_factory=list)
    evaluated_at_iso: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScopeBinding(SchemaModel):
    kind: ClassVar[str] = "ScopeBinding"

    child_type: ScopeType
    child_id: str
    parent_type: ScopeType
    parent_id: str

    @model_validator(mode="after")
    def reject_self_binding(self) -> "ScopeBinding":
        if self.child_type == self.parent_type and self.child_id == self.parent_id:
            raise ValueError("scope binding cannot reference itself")
        return self
