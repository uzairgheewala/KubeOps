from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from kubeops_core.models.tenancy import (
    AuthorizationDecision,
    AuthorizationRequest,
    RoleGrant,
    ScopeBinding,
)
from kubeops_core.util import utc_now_iso

ROLE_CAPABILITIES: dict[str, set[str]] = {
    "viewer": {"environment.read", "incident.read", "operation.read", "fleet.read", "pack.read"},
    "operator": {
        "environment.read", "incident.read", "operation.read", "operation.create", "operation.execute",
        "fleet.read", "fleet.operate", "pack.read", "executor.read",
    },
    "approver": {"operation.read", "operation.approve", "audit.read", "fleet.read"},
    "auditor": {"environment.read", "incident.read", "operation.read", "audit.read", "audit.export", "fleet.read", "pack.read"},
    "admin": {"*"},
}


class AuthorizationEngine:
    def __init__(self, grants: list[RoleGrant], bindings: list[ScopeBinding] | None = None) -> None:
        self.grants = grants
        self.bindings = bindings or []

    @staticmethod
    def _active(grant: RoleGrant, at: datetime) -> bool:
        if not grant.active:
            return False
        if grant.expires_at_iso:
            expires = datetime.fromisoformat(grant.expires_at_iso.replace("Z", "+00:00"))
            if expires <= at:
                return False
        return True

    def _ancestor_scopes(self, scope_type: str, scope_id: str) -> set[tuple[str, str]]:
        seen = {(scope_type, scope_id), ("global", "*")}
        changed = True
        while changed:
            changed = False
            for binding in self.bindings:
                child = (binding.child_type, binding.child_id)
                parent = (binding.parent_type, binding.parent_id)
                if child in seen and parent not in seen:
                    seen.add(parent)
                    changed = True
        return seen

    def evaluate(self, request: AuthorizationRequest, *, at: datetime | None = None) -> AuthorizationDecision:
        now = at or datetime.now(timezone.utc)
        scopes = self._ancestor_scopes(request.scope_type, request.scope_id)
        grants = [
            grant for grant in self.grants
            if grant.principal_id == request.principal_id
            and self._active(grant, now)
            and (grant.scope_type, grant.scope_id) in scopes
            and (not grant.environment_classes or request.environment_class in grant.environment_classes)
        ]
        roles = {grant.role for grant in grants}
        capabilities: set[str] = set()
        for grant in grants:
            capabilities.update(ROLE_CAPABILITIES.get(grant.role, set()))
            capabilities.update(grant.capabilities)
        required_roles_ok = not request.required_roles or bool(roles & request.required_roles) or "admin" in roles
        required_caps_ok = "*" in capabilities or request.required_capabilities.issubset(capabilities)
        if required_roles_ok and required_caps_ok:
            outcome = "allow"
            reasons = ["matching active role grant satisfied required role and capability constraints"]
        elif not grants:
            outcome = "deny"
            reasons = ["no active role grant covers the requested scope"]
        else:
            outcome = "deny"
            reasons = []
            if not required_roles_ok:
                reasons.append(f"required roles not satisfied: {sorted(request.required_roles)}")
            if not required_caps_ok:
                reasons.append(f"required capabilities not satisfied: {sorted(request.required_capabilities)}")
        return AuthorizationDecision(
            decision_id=f"authz:{uuid4()}",
            request_id=request.request_id,
            principal_id=request.principal_id,
            outcome=outcome,
            matched_grant_ids=[grant.grant_id for grant in grants],
            effective_roles=roles,
            effective_capabilities=capabilities,
            reasons=reasons,
            evaluated_at_iso=utc_now_iso(),
        )
