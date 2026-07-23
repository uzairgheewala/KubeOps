from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from kubeops_core.artifacts import build_audit_artifacts, build_fleet_artifacts, build_platform_backup_artifacts
from kubeops_core.distributed import DistributedDispatcher
from kubeops_core.fleet import FleetService
from kubeops_core.governance import AuditChain, RetentionPlanner
from kubeops_core.models import (
    ActionInstance,
    ActionTypeDefinition,
    AuditEvent,
    AuthorizationRequest,
    BackupComponent,
    ConcurrencyRule,
    ControlPlaneBackupManifest,
    ExecutionTask,
    ExecutorAgentDefinition,
    ExecutorHeartbeat,
    FleetDefinition,
    FleetEnvironmentStatus,
    MaintenanceWindow,
    ScheduledOperation,
    OrganizationDefinition,
    PackSignature,
    PackTrustPolicy,
    RateLimitRule,
    RetentionPolicy,
    RoleGrant,
    ScopeBinding,
    SecretReference,
    WorkspaceDefinition,
)
from kubeops_core.platform import PlatformRecoveryService
from kubeops_core.secrets import SecretResolver
from kubeops_core.supply_chain import PackSigner
from kubeops_core.tenancy import AuthorizationEngine
from kubeops_core.util import utc_now_iso

from .audit import append_audit_event
from .models import (
    ArtifactRecord,
    AuditEventRecord,
    EnvironmentRecord,
    EnvironmentSnapshotRecord,
    ExecutionTaskRecord,
    ExecutorAgentRecord,
    ExecutorHeartbeatRecord,
    FleetAssessmentRecord,
    FleetDependencyRecord,
    FleetMembershipRecord,
    FleetRecord,
    IncidentRecord,
    KnowledgePackRecord,
    MaintenanceWindowRecord,
    OperationRecord,
    OrganizationRecord,
    PackSignatureRecord,
    PackTrustPolicyRecord,
    PlatformBackupRecord,
    ConcurrencyRuleRecord,
    RateLimitRuleRecord,
    RetentionPolicyRecord,
    RoleGrantRecord,
    SecretReferenceRecord,
    ScheduledOperationRecord,
    TaskLeaseRecord,
    WorkspaceRecord,
)
from .services import (
    action_catalog, action_catalog_for_workspace, artifact_store, clear_service_caches, pack_manager,
    pack_runtime, pack_runtime_for_workspace,
)
from .scoping import enforce_payload_scope, requested_scope
from .scheduling import evaluate_schedule_record, materialize_schedule_record


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _default_scope() -> tuple[OrganizationRecord, WorkspaceRecord]:
    org, _ = OrganizationRecord.objects.get_or_create(
        organization_id=settings.KUBEOPS_DEFAULT_ORGANIZATION_ID,
        defaults={"name": "Default organization", "slug": "default", "payload": {}},
    )
    workspace, _ = WorkspaceRecord.objects.get_or_create(
        workspace_id=settings.KUBEOPS_DEFAULT_WORKSPACE_ID,
        defaults={"organization": org, "name": "Default workspace", "slug": "default", "payload": {}},
    )
    return org, workspace



def _request_scope_records(request):  # type: ignore[no-untyped-def]
    organization_id, workspace_id = requested_scope(request)
    organization = OrganizationRecord.objects.get(organization_id=organization_id, active=True)
    workspace = WorkspaceRecord.objects.select_related("organization").get(
        workspace_id=workspace_id, active=True
    )
    if workspace.organization_id != organization.pk:
        raise ValueError("requested workspace does not belong to requested organization")
    return organization, workspace


def _store_artifacts(
    artifacts, organization: OrganizationRecord, workspace: WorkspaceRecord
):  # type: ignore[no-untyped-def]
    store = artifact_store()
    rows = []
    for artifact in artifacts:
        path = store.put(artifact)
        ArtifactRecord.objects.update_or_create(
            artifact_id=artifact.artifact_id,
            defaults={
                "organization": organization,
                "workspace": workspace,
                "scope_type": artifact.scope_type,
                "scope_id": artifact.scope_id,
                "artifact_type": artifact.artifact_type,
                "content_hash": artifact.payload_hash,
                "media_type": artifact.media_type,
                "storage_path": str(path),
                "derived_from": artifact.derived_from,
                "metadata": artifact.metadata,
            },
        )
        rows.append({"artifact_id": artifact.artifact_id, "artifact_type": artifact.artifact_type, "content_hash": artifact.payload_hash})
    return rows


class OrganizationListView(APIView):
    required_roles = {"admin"}
    authorization_scope_type = "global"

    def get(self, request):  # type: ignore[no-untyped-def]
        return Response([item.payload for item in OrganizationRecord.objects.all()])

    def post(self, request):  # type: ignore[no-untyped-def]
        item = OrganizationDefinition.model_validate(request.data)
        record, _ = OrganizationRecord.objects.update_or_create(
            organization_id=item.organization_id,
            defaults={"name": item.name, "slug": item.slug, "active": item.active, "payload": item.model_dump(mode="json")},
        )
        return Response(record.payload, status=status.HTTP_201_CREATED)


class WorkspaceListView(APIView):
    required_roles = {"admin"}
    authorization_scope_type = "organization"

    def get(self, request):  # type: ignore[no-untyped-def]
        organization_id, _ = requested_scope(request)
        records = WorkspaceRecord.objects.select_related("organization").filter(organization__organization_id=organization_id)
        return Response([item.payload for item in records])

    def post(self, request):  # type: ignore[no-untyped-def]
        item = WorkspaceDefinition.model_validate(request.data)
        requested_organization, _ = requested_scope(request)
        if not request.user.is_superuser and item.organization_id != requested_organization:
            return Response({"detail": "workspace organization does not match request scope"}, status=status.HTTP_403_FORBIDDEN)
        organization = OrganizationRecord.objects.get(organization_id=item.organization_id)
        record, _ = WorkspaceRecord.objects.update_or_create(
            workspace_id=item.workspace_id,
            defaults={"organization": organization, "name": item.name, "slug": item.slug, "active": item.active, "payload": item.model_dump(mode="json")},
        )
        return Response(record.payload, status=status.HTTP_201_CREATED)


class RoleGrantListView(APIView):
    required_roles = {"admin"}
    authorization_scope_type = "global"

    def get(self, request):  # type: ignore[no-untyped-def]
        return Response([item.payload for item in RoleGrantRecord.objects.all()])

    def post(self, request):  # type: ignore[no-untyped-def]
        grant = RoleGrant.model_validate(request.data)
        record, _ = RoleGrantRecord.objects.update_or_create(
            grant_id=grant.grant_id,
            defaults={
                "principal_id": grant.principal_id, "role": grant.role, "scope_type": grant.scope_type,
                "scope_id": grant.scope_id, "active": grant.active,
                "expires_at": _dt(grant.expires_at_iso) if grant.expires_at_iso else None,
                "payload": grant.model_dump(mode="json"), "granted_at": _dt(grant.granted_at_iso),
            },
        )
        return Response(record.payload, status=status.HTTP_201_CREATED)


class AuthorizationEvaluateView(APIView):
    required_roles = {"admin", "auditor"}

    def post(self, request):  # type: ignore[no-untyped-def]
        auth_request = AuthorizationRequest.model_validate(request.data)
        grants = [RoleGrant.model_validate(item.payload) for item in RoleGrantRecord.objects.filter(principal_id=auth_request.principal_id, active=True)]
        bindings: list[ScopeBinding] = []
        for environment in EnvironmentRecord.objects.select_related("workspace", "organization"):
            if environment.workspace:
                bindings.append(ScopeBinding(child_type="environment", child_id=environment.environment_id, parent_type="workspace", parent_id=environment.workspace.workspace_id))
        for fleet in FleetRecord.objects.select_related("workspace"):
            bindings.append(ScopeBinding(child_type="fleet", child_id=fleet.fleet_id, parent_type="workspace", parent_id=fleet.workspace.workspace_id))
        for workspace in WorkspaceRecord.objects.select_related("organization"):
            bindings.append(ScopeBinding(child_type="workspace", child_id=workspace.workspace_id, parent_type="organization", parent_id=workspace.organization.organization_id))
        return Response(AuthorizationEngine(grants, bindings).evaluate(auth_request).model_dump(mode="json"))


class FleetListView(APIView):
    required_roles = {"viewer", "operator", "admin"}

    def get(self, request):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        return Response([item.payload for item in FleetRecord.objects.filter(workspace__workspace_id=workspace_id)])

    def post(self, request):  # type: ignore[no-untyped-def]
        fleet = FleetDefinition.model_validate(request.data)
        enforce_payload_scope(request, organization_id=fleet.organization_id, workspace_id=fleet.workspace_id)
        organization = OrganizationRecord.objects.get(organization_id=fleet.organization_id)
        workspace = WorkspaceRecord.objects.get(workspace_id=fleet.workspace_id)
        with transaction.atomic():
            record, _ = FleetRecord.objects.update_or_create(
                fleet_id=fleet.fleet_id,
                defaults={
                    "organization": organization, "workspace": workspace, "name": fleet.name,
                    "max_parallel_operations": fleet.max_parallel_operations, "active": fleet.active,
                    "payload": fleet.model_dump(mode="json"),
                },
            )
            record.memberships.all().delete()
            record.dependencies.all().delete()
            for member in fleet.members:
                member_environment = EnvironmentRecord.objects.get(
                    environment_id=member.environment_id, organization=organization, workspace=workspace
                )
                FleetMembershipRecord.objects.create(
                    fleet=record, environment=member_environment,
                    criticality=member.criticality, failure_domain=member.failure_domain,
                    payload=member.model_dump(mode="json"),
                )
            for dependency in fleet.dependencies:
                source_environment = EnvironmentRecord.objects.get(
                    environment_id=dependency.source_environment_id, organization=organization, workspace=workspace
                )
                target_environment = EnvironmentRecord.objects.get(
                    environment_id=dependency.target_environment_id, organization=organization, workspace=workspace
                )
                FleetDependencyRecord.objects.create(
                    dependency_id=dependency.dependency_id, fleet=record,
                    source_environment=source_environment,
                    target_environment=target_environment,
                    relationship_type=dependency.relationship_type, payload=dependency.model_dump(mode="json"),
                )
        return Response(record.payload, status=status.HTTP_201_CREATED)


class FleetDetailView(APIView):
    required_roles = {"viewer", "operator", "admin"}

    def get(self, request, fleet_id: str):  # type: ignore[no-untyped-def]
        return Response(FleetRecord.objects.get(fleet_id=fleet_id).payload)


class FleetAssessmentView(APIView):
    required_roles = {"viewer", "operator", "admin"}

    def post(self, request, fleet_id: str):  # type: ignore[no-untyped-def]
        record = FleetRecord.objects.get(fleet_id=fleet_id)
        fleet = FleetDefinition.model_validate(record.payload)
        statuses: list[FleetEnvironmentStatus] = []
        incident_families: dict[str, list[str]] = {}
        shared_factors: dict[str, dict[str, str]] = {}
        for member in fleet.members:
            environment = EnvironmentRecord.objects.get(environment_id=member.environment_id)
            snapshot = environment.snapshots.order_by("-captured_at").first()
            profile_statuses = {}
            if snapshot:
                profile_statuses = {item.profile_id: item.status for item in snapshot.assessments.all()}
            status_value = "unknown"
            values = set(profile_statuses.values())
            if values and values <= {"healthy", "not_applicable"}:
                status_value = "healthy"
            elif "unhealthy" in values:
                status_value = "degraded"
            active_incidents = list(environment.incidents.exclude(status="closed").values_list("incident_id", flat=True))
            active_operations = list(environment.operations.exclude(status__in=["completed", "failed", "cancelled"]).values_list("operation_id", flat=True))
            statuses.append(FleetEnvironmentStatus(
                environment_id=environment.environment_id, status=status_value,
                profile_statuses=profile_statuses, active_incident_ids=active_incidents,
                active_operation_ids=active_operations, source_snapshot_id=snapshot.snapshot_id if snapshot else None,
                observed_at_iso=snapshot.captured_at.isoformat() if snapshot else None,
            ))
            families: list[str] = []
            for incident in environment.incidents.exclude(status="closed"):
                families.extend(item.get("family_id") for item in incident.payload.get("hypotheses", []) if item.get("status") in {"root", "supported"} and item.get("family_id"))
            incident_families[environment.environment_id] = families
            shared_factors[environment.environment_id] = {
                "provider": environment.provider,
                "cluster_provider": environment.cluster_provider,
                "host_provider": environment.host_provider or "",
            }
        assessment = FleetService().assess(fleet, statuses, incident_families=incident_families, shared_factors=shared_factors)
        FleetAssessmentRecord.objects.update_or_create(
            assessment_id=assessment.assessment_id,
            defaults={"fleet": record, "status": assessment.status, "generated_at": _dt(assessment.generated_at_iso), "payload": assessment.model_dump(mode="json")},
        )
        artifacts = _store_artifacts(
            build_fleet_artifacts(assessment), record.organization, record.workspace
        )
        return Response({"assessment": assessment.model_dump(mode="json"), "artifacts": artifacts})


class FleetOperationPlanView(APIView):
    required_roles = {"operator", "admin"}

    def post(self, request, fleet_id: str):  # type: ignore[no-untyped-def]
        fleet = FleetDefinition.model_validate(FleetRecord.objects.get(fleet_id=fleet_id).payload)
        plan = FleetService().plan_operation(fleet, request.data.get("operation_type", "maintenance"))
        return Response(plan.model_dump(mode="json"))


class ExecutorAgentListView(APIView):
    required_roles = {"viewer", "operator", "admin"}

    def get(self, request):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        return Response([item.payload for item in ExecutorAgentRecord.objects.filter(workspace__workspace_id=workspace_id)])

    def post(self, request):  # type: ignore[no-untyped-def]
        agent = ExecutorAgentDefinition.model_validate(request.data)
        enforce_payload_scope(request, organization_id=agent.organization_id, workspace_id=agent.workspace_id)
        organization = OrganizationRecord.objects.get(organization_id=agent.organization_id)
        workspace = WorkspaceRecord.objects.get(workspace_id=agent.workspace_id, organization=organization)
        if agent.environment_ids and EnvironmentRecord.objects.filter(
            environment_id__in=agent.environment_ids
        ).exclude(organization=organization, workspace=workspace).exists():
            return Response({"detail": "agent environment scope mismatch"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        existing = ExecutorAgentRecord.objects.filter(agent_id=agent.agent_id).first()
        if existing is not None and (
            existing.organization_id != organization.pk
            or existing.workspace_id != workspace.pk
            or existing.public_identity != agent.public_identity
        ):
            return Response(
                {"detail": "agent identity is already bound to a different tenant or public identity"},
                status=status.HTTP_409_CONFLICT,
            )
        record, created = ExecutorAgentRecord.objects.update_or_create(
            agent_id=agent.agent_id,
            defaults={
                "organization": organization, "workspace": workspace, "name": agent.name, "status": agent.status,
                "capabilities": sorted(agent.capabilities), "supported_executor_ids": sorted(agent.supported_executor_ids),
                "environment_ids": sorted(agent.environment_ids), "max_concurrency": agent.max_concurrency,
                "last_heartbeat_at": _dt(agent.last_heartbeat_at_iso) if agent.last_heartbeat_at_iso else None,
                "public_identity": agent.public_identity, "payload": agent.model_dump(mode="json"),
            },
        )
        return Response(record.payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ExecutorHeartbeatView(APIView):
    required_capabilities = {"executor.heartbeat"}

    def post(self, request, agent_id: str):  # type: ignore[no-untyped-def]
        heartbeat = ExecutorHeartbeat.model_validate({**request.data, "agent_id": agent_id})
        agent = ExecutorAgentRecord.objects.get(agent_id=agent_id)
        agent.status = heartbeat.status
        agent.last_heartbeat_at = _dt(heartbeat.occurred_at_iso)
        agent.capabilities = sorted(set(agent.capabilities) | set(heartbeat.capabilities))
        payload = dict(agent.payload)
        payload.update({
            "status": heartbeat.status,
            "last_heartbeat_at_iso": heartbeat.occurred_at_iso,
            "capabilities": agent.capabilities,
            "available_capacity": heartbeat.available_capacity,
            "active_task_ids": heartbeat.active_task_ids,
            "heartbeat_diagnostics": heartbeat.diagnostics,
        })
        agent.payload = payload
        agent.save(update_fields=["status", "last_heartbeat_at", "capabilities", "payload", "updated_at"])
        ExecutorHeartbeatRecord.objects.create(
            heartbeat_id=heartbeat.heartbeat_id, agent=agent, status=heartbeat.status,
            occurred_at=_dt(heartbeat.occurred_at_iso), payload=heartbeat.model_dump(mode="json"),
        )
        return Response(agent.payload)


def _dispatcher_from_db() -> DistributedDispatcher:
    dispatcher = DistributedDispatcher()
    for record in ExecutorAgentRecord.objects.all():
        dispatcher.register_agent(ExecutorAgentDefinition.model_validate(record.payload))
    for record in ExecutionTaskRecord.objects.all():
        dispatcher.enqueue(ExecutionTask.model_validate(record.payload))
    return dispatcher


class ExecutionTaskListView(APIView):
    required_roles = {"operator", "admin"}

    def get(self, request):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        return Response([item.payload for item in ExecutionTaskRecord.objects.filter(workspace__workspace_id=workspace_id)])

    def post(self, request):  # type: ignore[no-untyped-def]
        task = ExecutionTask.model_validate(request.data)
        enforce_payload_scope(request, organization_id=task.organization_id, workspace_id=task.workspace_id)
        organization = OrganizationRecord.objects.get(organization_id=task.organization_id)
        workspace = WorkspaceRecord.objects.get(workspace_id=task.workspace_id, organization=organization)
        operation = OperationRecord.objects.get(operation_id=task.operation_id)
        environment = EnvironmentRecord.objects.get(environment_id=task.environment_id)
        if operation.environment_id != environment.pk:
            return Response({"detail": "task operation and environment do not match"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        if environment.organization_id != organization.pk or environment.workspace_id != workspace.pk:
            return Response({"detail": "task scope does not match its environment"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        payload_hash = hashlib.sha256(
            json.dumps(task.payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if payload_hash != task.payload_hash:
            return Response({"detail": "task payload hash mismatch"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        try:
            action = ActionInstance.model_validate(task.payload["action"])
            supplied_definition = ActionTypeDefinition.model_validate(task.payload["action_definition"])
            definition = action_catalog_for_workspace(task.workspace_id).validate_instance(action)
        except (KeyError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        if action.action_id != task.action_id or action.action_type_id != task.action_type_id:
            return Response({"detail": "task action identity mismatch"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        if supplied_definition.content_hash != definition.content_hash:
            return Response({"detail": "task action definition is not authoritative"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        mode = str(task.payload.get("mode", "dry_run"))
        expected_executor = "dry_run" if mode == "dry_run" else "simulation" if mode == "simulation" else definition.executor_id
        if task.executor_id != expected_executor:
            return Response({"detail": "task executor does not match execution mode"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        if mode == "live" and "live" not in definition.supported_modes:
            return Response({"detail": "action does not support live execution"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        required = set() if mode in {"dry_run", "simulation"} else set(definition.required_capabilities)
        if task.required_capabilities != required:
            return Response({"detail": "task capabilities do not match action requirements"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        if task.target_fingerprint and task.target_fingerprint != environment.fingerprint:
            return Response({"detail": "task target fingerprint mismatch"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        with transaction.atomic():
            existing = ExecutionTaskRecord.objects.select_for_update().filter(task_id=task.task_id).first()
            if existing is not None:
                if existing.payload_hash != task.payload_hash:
                    return Response(
                        {"detail": "task identity already exists with different content"},
                        status=status.HTTP_409_CONFLICT,
                    )
                return Response(existing.payload, status=status.HTTP_200_OK)
            record = ExecutionTaskRecord.objects.create(
                task_id=task.task_id, organization=organization, workspace=workspace,
                operation=operation, environment=environment,
                action_id=task.action_id, action_type_id=task.action_type_id,
                executor_id=task.executor_id, status=task.status, priority=task.priority,
                payload_hash=task.payload_hash, payload=task.model_dump(mode="json"),
                created_at=_dt(task.created_at_iso), updated_at=_dt(task.updated_at_iso),
            )
        return Response(record.payload, status=status.HTTP_201_CREATED)


class ExecutionTaskClaimView(APIView):
    required_capabilities = {"executor.claim"}

    def post(self, request, task_id: str):  # type: ignore[no-untyped-def]
        agent_id = str(request.data.get("agent_id", "")).strip()
        if not agent_id:
            return Response({"detail": "agent_id is required"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        organization_id, workspace_id = requested_scope(request)
        with transaction.atomic():
            task_record = (
                ExecutionTaskRecord.objects.select_for_update()
                .select_related("organization", "workspace")
                .get(task_id=task_id)
            )
            if (
                task_record.organization.organization_id != organization_id
                or task_record.workspace.workspace_id != workspace_id
            ):
                return Response({"detail": "task scope mismatch"}, status=status.HTTP_403_FORBIDDEN)
            if TaskLeaseRecord.objects.filter(task=task_record, status="active").exists():
                return Response({"detail": "task already has an active lease"}, status=status.HTTP_409_CONFLICT)
            agent_record = (
                ExecutorAgentRecord.objects.select_for_update()
                .get(agent_id=agent_id, organization=task_record.organization, workspace=task_record.workspace)
            )
            dispatcher = DistributedDispatcher()
            dispatcher.register_agent(ExecutorAgentDefinition.model_validate(agent_record.payload))
            dispatcher.enqueue(ExecutionTask.model_validate(task_record.payload))
            decision, lease = dispatcher.dispatch(task_id)
            if lease is None:
                return Response({"decision": decision.model_dump(mode="json")}, status=status.HTTP_409_CONFLICT)
            task = dispatcher.tasks[task_id]
            task_record.status = task.status
            task_record.assigned_agent = agent_record
            task_record.payload = task.model_dump(mode="json")
            task_record.updated_at = _dt(task.updated_at_iso)
            task_record.save(update_fields=["status", "assigned_agent", "payload", "updated_at"])
            TaskLeaseRecord.objects.create(
                lease_id=lease.lease_id, task=task_record, agent=agent_record, status=lease.status,
                nonce_hash=hashlib.sha256(lease.nonce.encode()).hexdigest(), acquired_at=_dt(lease.acquired_at_iso),
                expires_at=_dt(lease.expires_at_iso), heartbeat_at=_dt(lease.heartbeat_at_iso),
                payload=lease.model_dump(mode="json", exclude={"nonce"}),
            )
        return Response({"decision": decision.model_dump(mode="json"), "lease": lease.model_dump(mode="json")})


class ExecutionTaskCompleteView(APIView):
    required_capabilities = {"executor.complete"}

    def post(self, request, task_id: str):  # type: ignore[no-untyped-def]
        now = dj_timezone.now()
        with transaction.atomic():
            lease = (
                TaskLeaseRecord.objects.select_for_update()
                .select_related("task")
                .filter(task__task_id=task_id, status="active")
                .order_by("-acquired_at")
                .first()
            )
            if lease is None:
                return Response({"detail": "no active lease"}, status=status.HTTP_409_CONFLICT)
            nonce = request.data.get("nonce", "")
            if hashlib.sha256(nonce.encode()).hexdigest() != lease.nonce_hash:
                return Response({"detail": "invalid lease nonce"}, status=status.HTTP_403_FORBIDDEN)
            if lease.expires_at <= now:
                lease.status = "expired"
                lease.heartbeat_at = now
                lease.save(update_fields=["status", "heartbeat_at"])
                return Response({"detail": "lease has expired"}, status=status.HTTP_409_CONFLICT)
            success = bool(request.data.get("success", False))
            lease.status = "released"
            lease.heartbeat_at = now
            lease.save(update_fields=["status", "heartbeat_at"])
            task = lease.task
            task.status = "completed" if success else "failed"
            payload = dict(task.payload)
            payload.update({"status": task.status, "updated_at_iso": now.isoformat()})
            task.payload = payload
            task.updated_at = now
            task.save(update_fields=["status", "payload", "updated_at"])
        return Response(task.payload)


class AuditEventListView(APIView):
    required_roles = {"auditor", "admin"}

    def get(self, request):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        rows = AuditEventRecord.objects.filter(workspace__workspace_id=workspace_id).order_by("sequence")
        return Response([item.payload for item in rows])


class AuditVerifyView(APIView):
    required_roles = {"auditor", "admin"}

    def get(self, request):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        events = [AuditEvent.model_validate(item.payload) for item in AuditEventRecord.objects.filter(workspace__workspace_id=workspace_id).order_by("sequence")]
        return Response(AuditChain(events).verify().model_dump(mode="json"))


class AuditExportView(APIView):
    required_roles = {"auditor", "admin"}

    def post(self, request):  # type: ignore[no-untyped-def]
        organization_id, workspace_id = requested_scope(request)
        if request.data.get("organization_id") not in {None, organization_id} or request.data.get("workspace_id") not in {None, workspace_id}:
            return Response({"detail": "audit export scope does not match request scope"}, status=status.HTTP_403_FORBIDDEN)
        events = [AuditEvent.model_validate(item.payload) for item in AuditEventRecord.objects.filter(workspace__workspace_id=workspace_id).order_by("sequence")]
        chain = AuditChain(events)
        export, payload = chain.export(organization_id, workspace_id, format=request.data.get("format", "jsonl"))
        organization, workspace = _request_scope_records(request)
        artifacts = _store_artifacts(
            build_audit_artifacts(export, payload, chain.verify()), organization, workspace
        )
        return Response({"export": export.model_dump(mode="json"), "payload": payload, "artifacts": artifacts})


class MaintenanceWindowListView(APIView):
    required_roles_by_method = {"GET": {"admin", "auditor", "operator"}, "POST": {"admin"}}

    def get(self, request):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        return Response([
            item.payload for item in MaintenanceWindowRecord.objects.filter(
                workspace__workspace_id=workspace_id
            )
        ])

    def post(self, request):  # type: ignore[no-untyped-def]
        organization, workspace = _request_scope_records(request)
        payload = {
            **request.data,
            "organization_id": request.data.get("organization_id", organization.organization_id),
            "workspace_id": request.data.get("workspace_id", workspace.workspace_id),
        }
        window = MaintenanceWindow.model_validate(payload)
        enforce_payload_scope(
            request, organization_id=window.organization_id, workspace_id=window.workspace_id
        )
        if window.target_ids:
            environment_ids = set(
                EnvironmentRecord.objects.filter(
                    workspace=workspace, environment_id__in=window.target_ids
                ).values_list("environment_id", flat=True)
            )
            fleet_ids = set(
                FleetRecord.objects.filter(
                    workspace=workspace, fleet_id__in=window.target_ids
                ).values_list("fleet_id", flat=True)
            )
            missing = window.target_ids - environment_ids - fleet_ids
            if missing:
                return Response(
                    {"detail": f"unknown or cross-scope maintenance targets: {sorted(missing)}"},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
        record, _ = MaintenanceWindowRecord.objects.update_or_create(
            window_id=window.window_id,
            defaults={
                "organization": organization, "workspace": workspace, "enabled": window.enabled,
                "payload": window.model_dump(mode="json"),
            },
        )
        return Response(record.payload, status=status.HTTP_201_CREATED)


class ScheduledOperationListView(APIView):
    required_roles_by_method = {"GET": {"operator", "admin", "auditor"}, "POST": {"operator", "admin"}}
    required_capabilities_by_method = {"POST": {"operation.create"}}

    def get(self, request):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        return Response([
            item.payload for item in ScheduledOperationRecord.objects.filter(
                workspace__workspace_id=workspace_id
            )
        ])

    def post(self, request):  # type: ignore[no-untyped-def]
        organization, workspace = _request_scope_records(request)
        now = dj_timezone.now()
        payload = {
            **request.data,
            "schedule_id": request.data.get("schedule_id", f"schedule:{uuid4()}"),
            "organization_id": request.data.get("organization_id", organization.organization_id),
            "workspace_id": request.data.get("workspace_id", workspace.workspace_id),
            "created_by": request.data.get("created_by", str(request.user.pk)),
            "created_at_iso": request.data.get("created_at_iso", now.isoformat()),
            "updated_at_iso": now.isoformat(),
            "status": request.data.get("status", "pending"),
        }
        schedule = ScheduledOperation.model_validate(payload)
        enforce_payload_scope(
            request, organization_id=schedule.organization_id, workspace_id=schedule.workspace_id
        )
        environment = None
        fleet = None
        if schedule.target_type == "environment":
            environment = EnvironmentRecord.objects.filter(
                environment_id=schedule.target_id, workspace=workspace, active=True
            ).first()
            if environment is None:
                return Response({"detail": "scheduled environment not found in workspace"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        else:
            fleet = FleetRecord.objects.filter(fleet_id=schedule.target_id, workspace=workspace, active=True).first()
            if fleet is None:
                return Response({"detail": "scheduled fleet not found in workspace"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        window = None
        if schedule.maintenance_window_id:
            window = MaintenanceWindowRecord.objects.filter(
                window_id=schedule.maintenance_window_id, workspace=workspace
            ).first()
            if window is None:
                return Response({"detail": "maintenance window not found in workspace"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        record, _ = ScheduledOperationRecord.objects.update_or_create(
            schedule_id=schedule.schedule_id,
            defaults={
                "organization": organization, "workspace": workspace,
                "target_type": schedule.target_type, "target_id": schedule.target_id,
                "operation_type": schedule.operation_type, "status": schedule.status,
                "not_before": _dt(schedule.not_before_iso) if schedule.not_before_iso else None,
                "deadline": _dt(schedule.deadline_iso) if schedule.deadline_iso else None,
                "maintenance_window": window, "fleet": fleet,
                "payload": schedule.model_dump(mode="json"),
                "created_at": _dt(schedule.created_at_iso), "updated_at": _dt(schedule.updated_at_iso),
            },
        )
        evaluated, decision = evaluate_schedule_record(record)
        response_payload = evaluated.model_dump(mode="json")
        response_payload["decision"] = decision.model_dump(mode="json")
        return Response(response_payload, status=status.HTTP_201_CREATED)


class ScheduledOperationDetailView(APIView):
    required_roles = {"operator", "admin", "auditor"}

    def get(self, request, schedule_id: str):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        record = get_object_or_404(
            ScheduledOperationRecord, schedule_id=schedule_id, workspace__workspace_id=workspace_id
        )
        return Response(record.payload)


class ScheduledOperationEvaluateView(APIView):
    required_roles = {"operator", "admin", "auditor"}

    def post(self, request, schedule_id: str):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        record = get_object_or_404(
            ScheduledOperationRecord, schedule_id=schedule_id, workspace__workspace_id=workspace_id
        )
        schedule, decision = evaluate_schedule_record(record)
        return Response({"schedule": schedule.model_dump(mode="json"), "decision": decision.model_dump(mode="json")})


class ScheduledOperationMaterializeView(APIView):
    required_roles = {"operator", "admin"}
    required_capabilities = {"operation.create"}

    def post(self, request, schedule_id: str):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        record = get_object_or_404(
            ScheduledOperationRecord, schedule_id=schedule_id, workspace__workspace_id=workspace_id
        )
        schedule, decision, result = materialize_schedule_record(record)
        payload = {"schedule": schedule.model_dump(mode="json"), "decision": decision.model_dump(mode="json")}
        if result is not None and hasattr(result, "model_dump"):
            payload["result"] = result.model_dump(mode="json")
        response_status = status.HTTP_201_CREATED if schedule.status == "materialized" else status.HTTP_409_CONFLICT
        return Response(payload, status=response_status)


class ScheduledOperationCancelView(APIView):
    required_roles = {"operator", "admin"}

    def post(self, request, schedule_id: str):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        record = get_object_or_404(
            ScheduledOperationRecord, schedule_id=schedule_id, workspace__workspace_id=workspace_id
        )
        schedule = ScheduledOperation.model_validate(record.payload)
        if schedule.status == "materialized":
            return Response({"detail": "materialized schedules cannot be cancelled; cancel the operation instead"}, status=status.HTTP_409_CONFLICT)
        updated = schedule.model_copy(update={
            "status": "cancelled", "updated_at_iso": dj_timezone.now().isoformat(),
            "metadata": {**schedule.metadata, "cancellation_reason": request.data.get("reason", "cancelled by operator")},
        })
        record.status = updated.status
        record.payload = updated.model_dump(mode="json")
        record.updated_at = _dt(updated.updated_at_iso)
        record.save(update_fields=["status", "payload", "updated_at"])
        return Response(record.payload)


class RateLimitRuleListView(APIView):
    required_roles = {"admin", "auditor"}

    def get(self, request):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        return Response([item.payload for item in RateLimitRuleRecord.objects.filter(workspace__workspace_id=workspace_id)])

    def post(self, request):  # type: ignore[no-untyped-def]
        organization, workspace = _request_scope_records(request)
        rule = RateLimitRule.model_validate(request.data)
        if not request.user.is_superuser and (rule.scope_type != "workspace" or rule.scope_id != workspace.workspace_id):
            return Response({"detail": "rate rule scope does not match request workspace"}, status=status.HTTP_403_FORBIDDEN)
        record, _ = RateLimitRuleRecord.objects.update_or_create(
            rule_id=rule.rule_id,
            defaults={
                "organization": organization, "workspace": workspace, "operation": rule.operation,
                "enabled": rule.enabled, "payload": rule.model_dump(mode="json"),
            },
        )
        return Response(record.payload, status=status.HTTP_201_CREATED)


class ConcurrencyRuleListView(APIView):
    required_roles = {"admin", "auditor"}

    def get(self, request):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        return Response([item.payload for item in ConcurrencyRuleRecord.objects.filter(workspace__workspace_id=workspace_id)])

    def post(self, request):  # type: ignore[no-untyped-def]
        organization, workspace = _request_scope_records(request)
        rule = ConcurrencyRule.model_validate(request.data)
        if not request.user.is_superuser and (rule.scope_type != "workspace" or rule.scope_id != workspace.workspace_id):
            return Response({"detail": "concurrency rule scope does not match request workspace"}, status=status.HTTP_403_FORBIDDEN)
        record, _ = ConcurrencyRuleRecord.objects.update_or_create(
            rule_id=rule.rule_id,
            defaults={
                "organization": organization, "workspace": workspace,
                "operation_type": rule.operation_type, "enabled": rule.enabled,
                "payload": rule.model_dump(mode="json"),
            },
        )
        return Response(record.payload, status=status.HTTP_201_CREATED)


class RetentionPolicyListView(APIView):
    required_roles = {"admin", "auditor"}

    def get(self, request):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        return Response([item.payload for item in RetentionPolicyRecord.objects.filter(workspace__workspace_id=workspace_id)])

    def post(self, request):  # type: ignore[no-untyped-def]
        policy = RetentionPolicy.model_validate(request.data)
        enforce_payload_scope(request, organization_id=policy.organization_id, workspace_id=policy.scope_id)
        record, _ = RetentionPolicyRecord.objects.update_or_create(
            policy_id=policy.policy_id,
            defaults={
                "organization": OrganizationRecord.objects.get(organization_id=policy.organization_id),
                "workspace": WorkspaceRecord.objects.get(workspace_id=policy.scope_id),
                "enabled": policy.enabled, "payload": policy.model_dump(mode="json"),
            },
        )
        return Response(record.payload, status=status.HTTP_201_CREATED)


class RetentionPlanView(APIView):
    required_roles = {"admin", "auditor"}

    def post(self, request):  # type: ignore[no-untyped-def]
        policy_record = RetentionPolicyRecord.objects.get(policy_id=request.data["policy_id"])
        policy = RetentionPolicy.model_validate(policy_record.payload)
        resources: list[dict[str, object]] = []
        resources.extend(
            {
                "resource_type": "artifact",
                "resource_id": item.artifact_id,
                "created_at_iso": item.created_at.isoformat(),
                "size_bytes": Path(item.storage_path).stat().st_size if Path(item.storage_path).exists() else 0,
                "labels": item.metadata,
            }
            for item in ArtifactRecord.objects.filter(workspace=policy_record.workspace)
        )
        resources.extend({"resource_type": "snapshot", "resource_id": item.snapshot_id, "created_at_iso": item.created_at.isoformat()} for item in EnvironmentSnapshotRecord.objects.filter(environment__workspace=policy_record.workspace))
        resources.extend({"resource_type": "incident", "resource_id": item.incident_id, "created_at_iso": item.persisted_at.isoformat(), "has_certificate": bool(item.certificate_status)} for item in IncidentRecord.objects.filter(environment__workspace=policy_record.workspace))
        resources.extend({"resource_type": "operation", "resource_id": item.operation_id, "created_at_iso": item.persisted_at.isoformat(), "status": item.status, "has_certificate": bool(item.certificate_status)} for item in OperationRecord.objects.filter(environment__workspace=policy_record.workspace))
        plan = RetentionPlanner().plan(policy, resources)
        return Response(plan.model_dump(mode="json"))


class PackSignView(APIView):
    required_roles = {"admin"}

    def post(self, request, pack_id: str):  # type: ignore[no-untyped-def]
        manifest = pack_manager().get(pack_id)
        secret_ref = SecretReference.model_validate(request.data["secret_reference"])
        enforce_payload_scope(request, organization_id=secret_ref.organization_id, workspace_id=secret_ref.workspace_id)
        SecretReferenceRecord.objects.update_or_create(
            secret_ref_id=secret_ref.secret_ref_id,
            defaults={
                "organization": OrganizationRecord.objects.get(organization_id=secret_ref.organization_id),
                "workspace": WorkspaceRecord.objects.get(workspace_id=secret_ref.workspace_id),
                "provider": secret_ref.provider, "locator_redacted": SecretResolver._redact(secret_ref.locator),
                "purpose": secret_ref.purpose, "payload": secret_ref.model_dump(mode="json", exclude={"locator"}),
            },
        )
        secret, _ = SecretResolver().resolve(secret_ref, "pack-signer")
        signature = PackSigner.sign(
            manifest, key_id=request.data.get("key_id", settings.KUBEOPS_PACK_TRUST_KEY_ID),
            secret=secret, signer=request.data.get("signer", str(request.user)),
            scheme=request.data.get("scheme", "ed25519"),
        )
        pack_record = KnowledgePackRecord.objects.get(pack_id=pack_id)
        PackSignatureRecord.objects.create(
            signature_id=signature.signature_id, pack=pack_record, scheme=signature.scheme,
            key_id=signature.key_id, signer=signature.signer, signature=signature.signature,
            manifest_hash=signature.manifest_hash, signed_at=_dt(signature.signed_at_iso), payload=signature.model_dump(mode="json"),
        )
        clear_service_caches()
        return Response(signature.model_dump(mode="json"), status=status.HTTP_201_CREATED)


class PackVerifyView(APIView):
    required_roles = {"viewer", "auditor", "admin"}

    def post(self, request, pack_id: str):  # type: ignore[no-untyped-def]
        manifest = pack_manager().get(pack_id)
        policy = PackTrustPolicy.model_validate(request.data["policy"])
        enforce_payload_scope(request, organization_id=policy.organization_id, workspace_id=policy.workspace_id)
        PackTrustPolicyRecord.objects.update_or_create(
            policy_id=policy.policy_id,
            defaults={
                "organization": OrganizationRecord.objects.get(organization_id=policy.organization_id),
                "workspace": WorkspaceRecord.objects.get(workspace_id=policy.workspace_id),
                "payload": policy.model_dump(mode="json"),
            },
        )
        record = PackSignatureRecord.objects.filter(pack__pack_id=pack_id).order_by("-signed_at").first()
        signature = PackSignature.model_validate(record.payload) if record else None
        trusted_secrets: dict[str, str] = {}
        trusted_public_keys: dict[str, str] = {}
        secret_value = os.getenv(settings.KUBEOPS_PACK_TRUST_SECRET_ENV)
        if secret_value:
            trusted_secrets[settings.KUBEOPS_PACK_TRUST_KEY_ID] = secret_value
        public_value = os.getenv(settings.KUBEOPS_PACK_TRUST_PUBLIC_KEY_ENV)
        if public_value:
            trusted_public_keys[settings.KUBEOPS_PACK_TRUST_KEY_ID] = public_value.replace("\\n", "\n")
        result = PackSigner.verify(
            manifest, signature, policy, trusted_secrets=trusted_secrets,
            trusted_public_keys=trusted_public_keys,
        )
        clear_service_caches()
        return Response(result.model_dump(mode="json"))


class PlatformBackupListView(APIView):
    required_roles = {"admin", "auditor"}

    def get(self, request):  # type: ignore[no-untyped-def]
        _, workspace_id = requested_scope(request)
        return Response([item.payload for item in PlatformBackupRecord.objects.filter(workspace__workspace_id=workspace_id)])

    def post(self, request):  # type: ignore[no-untyped-def]
        org, workspace = _request_scope_records(request)
        pack_resolution = pack_runtime_for_workspace(workspace.workspace_id).resolution
        audit_head = AuditEventRecord.objects.filter(workspace=workspace).order_by("-sequence").values_list("event_hash", flat=True).first()
        components = [
            BackupComponent(component_id="database", component_type="database", source=str(settings.DATABASES["default"]["ENGINE"]), payload_hash=request.data.get("database_hash", "external-backup-required")),
            BackupComponent(component_id="artifact-store", component_type="artifact_store", source=str(settings.KUBEOPS_ARTIFACT_DIR), payload_hash=request.data.get("artifact_store_hash", "inventory-required")),
            BackupComponent(component_id="configuration", component_type="configuration", source=str(settings.REPO_ROOT), payload_hash=pack_resolution.content_hash),
        ]
        manifest = PlatformRecoveryService().build_backup_manifest(
            organization_id=org.organization_id, workspace_id=workspace.workspace_id, kubeops_version="1.0.0",
            schema_version="0006", components=components, pack_resolution_hash=pack_resolution.content_hash,
            audit_head_hash=audit_head, database_vendor=settings.DATABASES["default"]["ENGINE"],
        )
        PlatformBackupRecord.objects.create(
            backup_id=manifest.backup_id, organization=org, workspace=workspace, status=manifest.status,
            manifest_hash=manifest.manifest_hash, created_at=_dt(manifest.created_at_iso), payload=manifest.model_dump(mode="json"),
        )
        artifacts = _store_artifacts(build_platform_backup_artifacts(manifest), org, workspace)
        return Response({"backup": manifest.model_dump(mode="json"), "artifacts": artifacts}, status=status.HTTP_201_CREATED)


class PlatformRestorePlanView(APIView):
    required_roles = {"admin"}

    def post(self, request):  # type: ignore[no-untyped-def]
        _, workspace = _request_scope_records(request)
        backup = PlatformBackupRecord.objects.get(backup_id=request.data["backup_id"], workspace=workspace)
        manifest = ControlPlaneBackupManifest.model_validate(backup.payload)
        plan = PlatformRecoveryService().restore_plan(manifest, target_version=request.data.get("target_version", "1.0.0"))
        return Response(plan.model_dump(mode="json"))


class PlatformReadinessView(APIView):
    required_roles = {"admin", "auditor"}

    def get(self, request):  # type: ignore[no-untyped-def]
        _, workspace = _request_scope_records(request)
        events = [AuditEvent.model_validate(item.payload) for item in workspace.audit_events.order_by("sequence")]
        report = PlatformRecoveryService().upgrade_readiness(
            current_version="1.0.0", target_version=request.query_params.get("target_version", "1.0.0"),
            database_migrations_pending=int(request.query_params.get("database_migrations_pending", 0)),
            unresolved_pack_issues=sum(len(item.validation_issues) for item in KnowledgePackRecord.objects.filter(enabled=True)),
            audit_chain_valid=AuditChain(events).verify().valid,
            recent_verified_backup=workspace.platform_backups.filter(status="verified").exists(),
            active_operations=OperationRecord.objects.filter(environment__workspace=workspace).exclude(status__in=["completed", "failed", "cancelled"]).count(),
        )
        return Response(report.model_dump(mode="json"))

class CurrentIdentityView(APIView):
    """Return the authenticated principal without exposing credential material."""

    def get(self, request):  # type: ignore[no-untyped-def]
        user = request.user
        return Response({
            "principal_id": str(user.pk),
            "username": user.get_username(),
            "is_superuser": bool(user.is_superuser),
            "is_staff": bool(user.is_staff),
            "organization_id": request.headers.get("X-KubeOps-Organization", settings.KUBEOPS_DEFAULT_ORGANIZATION_ID),
            "workspace_id": request.headers.get("X-KubeOps-Workspace", settings.KUBEOPS_DEFAULT_WORKSPACE_ID),
        })
