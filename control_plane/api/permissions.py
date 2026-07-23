from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from rest_framework.permissions import BasePermission, SAFE_METHODS

from kubeops_core.models import AuthorizationRequest, RoleGrant, ScopeBinding
from kubeops_core.tenancy import AuthorizationEngine

from .models import (
    EnvironmentRecord,
    EnvironmentSnapshotRecord,
    ExecutionTaskRecord,
    ExecutorAgentRecord,
    FleetRecord,
    IncidentRecord,
    OperationRecord,
    RoleGrantRecord,
)


class KubeOpsRolePermission(BasePermission):
    """Hierarchical, object-aware organization/workspace authorization."""

    def has_permission(self, request, view) -> bool:  # type: ignore[no-untyped-def]
        if getattr(view, "public_access", False):
            return True
        if request.method in SAFE_METHODS and settings.KUBEOPS_ALLOW_ANONYMOUS_READ and not request.user.is_authenticated:
            return True
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        principal_id = str(request.user.pk)
        grants = [
            RoleGrant.model_validate(item.payload)
            for item in RoleGrantRecord.objects.filter(principal_id=principal_id, active=True)
        ]
        roles_by_method = getattr(view, "required_roles_by_method", {})
        capabilities_by_method = getattr(view, "required_capabilities_by_method", {})
        required_roles = set(roles_by_method.get(request.method, getattr(view, "required_roles", [])))
        required_capabilities = set(
            capabilities_by_method.get(request.method, getattr(view, "required_capabilities", []))
        )
        if not required_roles:
            required_roles = {"viewer"} if request.method in SAFE_METHODS else {"operator", "admin"}
        scope_type, scope_id, environment_class, bindings = self._scope(request, view)
        decision = AuthorizationEngine(grants, bindings).evaluate(
            AuthorizationRequest(
                request_id=f"authz:{uuid4()}",
                principal_id=principal_id,
                action=f"{request.method}:{request.path}",
                scope_type=scope_type,
                scope_id=scope_id,
                required_roles=required_roles,
                required_capabilities=required_capabilities,
                environment_class=environment_class,
            )
        )
        request.kubeops_authorization = decision
        return decision.outcome == "allow"

    @classmethod
    def _scope(cls, request, view):  # type: ignore[no-untyped-def]
        workspace_id = request.headers.get(
            "X-KubeOps-Workspace", settings.KUBEOPS_DEFAULT_WORKSPACE_ID
        )
        organization_id = request.headers.get(
            "X-KubeOps-Organization", settings.KUBEOPS_DEFAULT_ORGANIZATION_ID
        )
        bindings = [
            ScopeBinding(
                child_type="workspace",
                child_id=workspace_id,
                parent_type="organization",
                parent_id=organization_id,
            )
        ]

        explicit_scope = getattr(view, "authorization_scope_type", None)
        if explicit_scope == "global":
            return "global", "*", None, bindings
        if explicit_scope == "organization":
            return "organization", organization_id, None, bindings

        record = cls._object_record(view.kwargs)
        if record is not None:
            object_workspace = getattr(record, "workspace", None)
            object_environment = getattr(record, "environment", None)
            if object_workspace is None and object_environment is not None:
                object_workspace = object_environment.workspace
            if object_workspace is not None:
                workspace_id = object_workspace.workspace_id
                organization_id = object_workspace.organization.organization_id
                bindings = [
                    ScopeBinding(
                        child_type="workspace",
                        child_id=workspace_id,
                        parent_type="organization",
                        parent_id=organization_id,
                    )
                ]
            if isinstance(record, EnvironmentRecord):
                bindings.append(
                    ScopeBinding(
                        child_type="environment",
                        child_id=record.environment_id,
                        parent_type="workspace",
                        parent_id=workspace_id,
                    )
                )
                return "environment", record.environment_id, record.environment_class, bindings
            if isinstance(record, FleetRecord):
                bindings.append(
                    ScopeBinding(
                        child_type="fleet",
                        child_id=record.fleet_id,
                        parent_type="workspace",
                        parent_id=workspace_id,
                    )
                )
                return "fleet", record.fleet_id, None, bindings
            if isinstance(record, OperationRecord):
                bindings.extend(
                    [
                        ScopeBinding(
                            child_type="environment",
                            child_id=record.environment.environment_id,
                            parent_type="workspace",
                            parent_id=workspace_id,
                        ),
                        ScopeBinding(
                            child_type="operation",
                            child_id=record.operation_id,
                            parent_type="environment",
                            parent_id=record.environment.environment_id,
                        ),
                    ]
                )
                return "operation", record.operation_id, record.environment.environment_class, bindings
            if isinstance(record, (EnvironmentSnapshotRecord, IncidentRecord)):
                environment = record.environment
                bindings.append(
                    ScopeBinding(
                        child_type="environment",
                        child_id=environment.environment_id,
                        parent_type="workspace",
                        parent_id=workspace_id,
                    )
                )
                return "environment", environment.environment_id, environment.environment_class, bindings
            if isinstance(record, ExecutionTaskRecord):
                operation = record.operation
                bindings.extend(
                    [
                        ScopeBinding(
                            child_type="environment",
                            child_id=record.environment.environment_id,
                            parent_type="workspace",
                            parent_id=workspace_id,
                        ),
                        ScopeBinding(
                            child_type="operation",
                            child_id=operation.operation_id,
                            parent_type="environment",
                            parent_id=record.environment.environment_id,
                        ),
                    ]
                )
                return "operation", operation.operation_id, record.environment.environment_class, bindings
            if isinstance(record, ExecutorAgentRecord):
                return "workspace", workspace_id, None, bindings

        environment_id = view.kwargs.get("environment_id")
        if not environment_id and hasattr(request, "data"):
            environment_id = request.data.get("environment_id")
        fleet_id = view.kwargs.get("fleet_id")
        if environment_id:
            environment = EnvironmentRecord.objects.filter(environment_id=environment_id).first()
            if environment and environment.workspace:
                workspace_id = environment.workspace.workspace_id
                organization_id = environment.workspace.organization.organization_id
                bindings = [
                    ScopeBinding(
                        child_type="workspace",
                        child_id=workspace_id,
                        parent_type="organization",
                        parent_id=organization_id,
                    )
                ]
            bindings.append(
                ScopeBinding(
                    child_type="environment",
                    child_id=environment_id,
                    parent_type="workspace",
                    parent_id=workspace_id,
                )
            )
            return "environment", environment_id, environment.environment_class if environment else None, bindings
        if fleet_id:
            fleet = FleetRecord.objects.filter(fleet_id=fleet_id).first()
            if fleet:
                workspace_id = fleet.workspace.workspace_id
                organization_id = fleet.organization.organization_id
                bindings = [
                    ScopeBinding(
                        child_type="workspace",
                        child_id=workspace_id,
                        parent_type="organization",
                        parent_id=organization_id,
                    )
                ]
            bindings.append(
                ScopeBinding(
                    child_type="fleet",
                    child_id=fleet_id,
                    parent_type="workspace",
                    parent_id=workspace_id,
                )
            )
            return "fleet", fleet_id, None, bindings
        return "workspace", workspace_id, None, bindings

    @staticmethod
    def _object_record(kwargs):  # type: ignore[no-untyped-def]
        lookups = [
            ("operation_id", OperationRecord, "operation_id"),
            ("snapshot_id", EnvironmentSnapshotRecord, "snapshot_id"),
            ("incident_id", IncidentRecord, "incident_id"),
            ("task_id", ExecutionTaskRecord, "task_id"),
            ("agent_id", ExecutorAgentRecord, "agent_id"),
            ("fleet_id", FleetRecord, "fleet_id"),
            ("environment_id", EnvironmentRecord, "environment_id"),
        ]
        for kwarg, model, field in lookups:
            value = kwargs.get(kwarg)
            if value:
                query = {field: value}
                return model.objects.select_related().filter(**query).first()
        return None
