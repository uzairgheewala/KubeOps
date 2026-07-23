from __future__ import annotations

import hashlib
import json

from typing import Any

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from pydantic import ValidationError
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from kubeops_core import __version__ as core_version
from kubeops_core.artifacts import build_incident_artifacts, build_operation_artifacts, build_run_artifacts, build_snapshot_artifacts
from kubeops_core.discovery import diff_snapshots, export_discovery_fixture
from kubeops_core.health import HealthAssessmentEngine
from kubeops_core.execution import ExecutionContext, RuntimeContext
from kubeops_core.policy import PolicyContext
from kubeops_core.util import utc_now_iso
from kubeops_core.models import (
    AccessMethodDefinition,
    AccessValidationResult,
    ActionInstance,
    ActionReceipt,
    ApprovalRecord,
    ActionTypeDefinition,
    CausalEdge,
    CausalTemplate,
    CollectorDefinition,
    CollectorRunResult,
    CompiledOperationalProfile,
    DiagnosticCaseResult,
    DiagnosticEvaluationReport,
    DiagnosticExpectation,
    DiagnosisCertificate,
    DiscoveryBundle,
    EnvironmentDefinition,
    EnvironmentSnapshot,
    EvidenceCollectionPlan,
    EvidenceFact,
    EvidenceIntent,
    ExecutionPolicy,
    Hypothesis,
    KnowledgePackManifest,
    PackCompatibility,
    PackContributions,
    PackCoverageReport,
    PackDependency,
    PackResolution,
    PackScenarioCoverage,
    PackStatus,
    PackValidationIssue,
    EntityClassifierRule,
    RelationshipResolverRule,
    RedactionRule,
    IncidentInvestigation,
    IncidentTimelineEntry,
    InvariantDefinition,
    Observation,
    ObservationProfile,
    OperationalArtifact,
    OperationalEntity,
    OperationalObjective,
    OperationalProfile,
    OperationalProfileAssessment,
    OperationalProfileSpec,
    OperationRun,
    LifecycleProfile,
    PolicyDecision,
    ProbeIntent,
    ProbePlan,
    ProbeRun,
    RecoveryCertificate,
    RecoveryPlan,
    Relationship,
    RunArtifact,
    ScenarioComposition,
    ScenarioFamily,
    ScenarioInstance,
    SimulationRun,
    SnapshotDiff,
    Symptom,
    TopologyGraph,
    VerificationCondition,
    VerificationResult,
    ExecutionCheckpoint,
    OperationEvent,
)
from kubeops_core.models import (
    AuditChainVerification, AuditEvent, AuditExport, AuthorizationDecision, AuthorizationRequest,
    BackupComponent, CommonCauseFinding, ConcurrencyRule, ControlPlaneBackupManifest,
    ControlPlaneRestorePlan, DispatchDecision, ExecutionTask, ExecutorAgentDefinition, ExecutorHeartbeat,
    FleetAssessment, FleetDefinition, FleetDependency, FleetEnvironmentStatus, FleetMember, FleetOperationPlan,
    FleetOperationWave, GovernanceDecision, OrganizationDefinition, PackSignature, PackTrustPolicy,
    PackVerificationResult, RateLimitRule, RetentionCandidate, RetentionPlan, RetentionPolicy, RoleGrant,
    ScopeBinding, SecretReference, SecretResolutionReceipt, TaskLease, UpgradeReadinessCheck,
    UpgradeReadinessReport, WorkspaceDefinition, RestoreStep, MaintenanceWindow, ScheduledOperation, ScheduleDecision,
)
from kubeops_core.scenarios import ScenarioCompileError, ScenarioComposer
from kubeops_core.topology import TopologyCompiler

from .scoping import enforce_payload_scope, requested_scope
from .governance import evaluate_governance, mark_governance_usage_terminal

from .models import (
    AccessValidationRecord,
    ArtifactRecord,
    DiagnosisCertificateRecord,
    EvidenceFactRecord,
    EnvironmentRecord,
    EnvironmentSnapshotRecord,
    HypothesisRecord,
    IncidentRecord,
    IncidentTimelineRecord,
    OperationEventRecord,
    OperationRecord,
    OrganizationRecord,
    OperationPolicyDecisionRecord,
    OperationApprovalRecord,
    ActionReceiptRecord,
    OperationTimelineRecord,
    ExecutionCheckpointRecord,
    OperationVerificationRecord,
    RecoveryCertificateRecord,
    KnowledgePackRecord,
    LifecycleProfileRecord,
    ExecutionPolicyRecord,
    ExecutionTaskRecord,
    ExecutorAgentRecord,
    FleetRecord,
    OperationalProfileRecord,
    ProfileAssessmentRecord,
    ProbeRunRecord,
    ScenarioRunRecord,
    SnapshotEntityRecord,
    SnapshotRelationshipRecord,
    WorkspaceRecord,
)
from .services import (
    action_catalog,
    action_catalog_for_workspace,
    artifact_store,
    diagnostic_catalog,
    diagnostic_catalog_for_workspace,
    environment_intelligence,
    environment_intelligence_for_workspace,
    investigation_service,
    investigation_service_for_workspace,
    lifecycle_planner,
    lifecycle_planner_for_workspace,
    lifecycle_registry,
    lifecycle_registry_for_workspace,
    operation_runtime,
    operation_runtime_for_workspace,
    policy_registry,
    profile_registry,
    profile_registry_for_workspace,
    registry_catalog, registry_catalog_for_workspace,
    scenario_compiler,
    scenario_diagnosis_evaluator, scenario_diagnosis_evaluator_for_workspace,
    scenario_registry,
    simulation_engine,
    pack_manager,
    pack_runtime,
    pack_runtime_for_workspace,
    resolve_pack_runtime_for_workspace,
)


def _dt(value: str):
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValueError(f"invalid ISO datetime {value!r}")
    return parsed


def _validation_error(exc: ValidationError) -> Response:
    return Response(
        {"errors": [f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in exc.errors()]},
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


def _record_workspace_id(record: EnvironmentRecord) -> str:
    if record.workspace is not None:
        return record.workspace.workspace_id
    return settings.KUBEOPS_DEFAULT_WORKSPACE_ID


def _request_scope_records(request: Request) -> tuple[OrganizationRecord, WorkspaceRecord]:
    organization_id, workspace_id = requested_scope(request)
    organization = get_object_or_404(OrganizationRecord, organization_id=organization_id, active=True)
    workspace = get_object_or_404(
        WorkspaceRecord.objects.select_related("organization"), workspace_id=workspace_id, active=True
    )
    if workspace.organization_id != organization.pk:
        raise ValueError("requested workspace does not belong to requested organization")
    return organization, workspace


def _environment(record: EnvironmentRecord) -> EnvironmentDefinition:
    return EnvironmentDefinition.model_validate(record.payload)


def _snapshot(record: EnvironmentSnapshotRecord) -> EnvironmentSnapshot:
    return EnvironmentSnapshot.model_validate(record.payload)


def _persist_run(
    scenario: ScenarioInstance, run: SimulationRun, organization: OrganizationRecord, workspace: WorkspaceRecord
) -> list[dict[str, str]]:
    artifacts = build_run_artifacts(scenario, run)
    paths = {artifact.artifact_id: artifact_store().put(artifact) for artifact in artifacts}
    with transaction.atomic():
        run_record = ScenarioRunRecord.objects.create(
            organization=organization,
            workspace=workspace,
            run_id=run.run_id,
            scenario_id=run.scenario_id,
            family_id=run.family_id,
            status=run.status,
            scenario_payload=scenario.model_dump(mode="json"),
            run_payload=run.model_dump(mode="json"),
            completed_at=_dt(run.completed_at_iso) if run.completed_at_iso else None,
        )
        OperationEventRecord.objects.bulk_create(
            [
                OperationEventRecord(
                    run=run_record,
                    sequence=event.sequence,
                    event_type=event.event_type,
                    occurred_at_seconds=event.at_seconds,
                    payload=event.model_dump(mode="json"),
                )
                for event in run.timeline
            ]
        )
        ArtifactRecord.objects.bulk_create(
            [
                ArtifactRecord(
                    organization=organization,
                    workspace=workspace,
                    artifact_id=artifact.artifact_id,
                    run=run_record,
                    scope_type="simulation_run",
                    scope_id=run.run_id,
                    artifact_type=artifact.artifact_type,
                    content_hash=artifact.payload_hash,
                    media_type=artifact.media_type,
                    storage_path=str(paths[artifact.artifact_id]),
                    derived_from=artifact.derived_from,
                )
                for artifact in artifacts
            ]
        )
    return [
        {"artifact_id": artifact.artifact_id, "artifact_type": artifact.artifact_type, "content_hash": artifact.payload_hash}
        for artifact in artifacts
    ]


def _persist_environment(environment: EnvironmentDefinition, *, update: bool = False) -> EnvironmentRecord:
    organization, _ = OrganizationRecord.objects.get_or_create(
        organization_id=environment.organization_id,
        defaults={
            "name": environment.organization_id.replace("-", " ").title(),
            "slug": environment.organization_id,
            "payload": {
                "organization_id": environment.organization_id,
                "name": environment.organization_id.replace("-", " ").title(),
                "slug": environment.organization_id,
            },
        },
    )
    workspace, _ = WorkspaceRecord.objects.get_or_create(
        workspace_id=environment.workspace_id,
        defaults={
            "organization": organization,
            "name": environment.workspace_id.replace("-", " ").title(),
            "slug": environment.workspace_id,
            "payload": {
                "workspace_id": environment.workspace_id,
                "organization_id": organization.organization_id,
                "name": environment.workspace_id.replace("-", " ").title(),
                "slug": environment.workspace_id,
            },
        },
    )
    if workspace.organization_id != organization.pk:
        raise ValueError("environment workspace belongs to a different organization")
    defaults = {
        "organization": organization,
        "workspace": workspace,
        "name": environment.name,
        "environment_class": environment.environment_class,
        "provider": environment.provider,
        "cluster_provider": environment.cluster_provider,
        "host_provider": environment.host_provider,
        "criticality": environment.criticality,
        "fingerprint": environment.content_hash,
        "payload": environment.model_dump(mode="json"),
        "active": True,
    }
    if update:
        record, _ = EnvironmentRecord.objects.update_or_create(environment_id=environment.environment_id, defaults=defaults)
        return record
    return EnvironmentRecord.objects.create(environment_id=environment.environment_id, **defaults)


def _persist_validation(record: EnvironmentRecord, result: AccessValidationResult) -> AccessValidationRecord:
    return AccessValidationRecord.objects.create(
        validation_id=result.validation_id,
        environment=record,
        access_method_id=result.access_method_id,
        status=result.status,
        target_fingerprint=result.target_fingerprint,
        payload=result.model_dump(mode="json"),
        checked_at=_dt(result.checked_at_iso),
    )


def _persist_snapshot(
    environment_record: EnvironmentRecord,
    bundle: DiscoveryBundle,
    snapshot: EnvironmentSnapshot,
    topology: TopologyGraph,
    assessments: list[OperationalProfileAssessment],
    snapshot_diff: SnapshotDiff | None,
) -> tuple[EnvironmentSnapshotRecord, list[dict[str, str]]]:
    artifacts = build_snapshot_artifacts(bundle, snapshot, topology, assessments, snapshot_diff)
    paths = {artifact.artifact_id: artifact_store().put(artifact) for artifact in artifacts}
    with transaction.atomic():
        snapshot_record = EnvironmentSnapshotRecord.objects.create(
            snapshot_id=snapshot.snapshot_id,
            environment=environment_record,
            status=snapshot.status,
            source_type=snapshot.source_type,
            source_fingerprint=snapshot.source_fingerprint,
            captured_at=_dt(snapshot.captured_at_iso),
            started_at=_dt(snapshot.started_at_iso),
            completed_at=_dt(snapshot.completed_at_iso),
            content_hash=snapshot.content_hash,
            payload=snapshot.model_dump(mode="json"),
            summary=snapshot.collection_summary,
        )
        SnapshotEntityRecord.objects.bulk_create(
            [
                SnapshotEntityRecord(
                    snapshot=snapshot_record,
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    name=entity.name,
                    plane=entity.plane,
                    namespace=entity.namespace,
                    provider=entity.provider,
                    labels=entity.labels,
                    desired_state=entity.desired_state,
                    observed_state=entity.observed_state,
                    content_hash=entity.content_hash,
                    payload=entity.model_dump(mode="json"),
                )
                for entity in snapshot.entities
            ]
        )
        SnapshotRelationshipRecord.objects.bulk_create(
            [
                SnapshotRelationshipRecord(
                    snapshot=snapshot_record,
                    relationship_id=relationship.relationship_id,
                    source_id=relationship.source_id,
                    target_id=relationship.target_id,
                    relationship_type=relationship.relationship_type,
                    confidence=relationship.confidence,
                    provenance=relationship.provenance,
                    content_hash=relationship.content_hash,
                    payload=relationship.model_dump(mode="json"),
                )
                for relationship in snapshot.relationships
            ]
        )
        ProfileAssessmentRecord.objects.bulk_create(
            [
                ProfileAssessmentRecord(
                    assessment_id=assessment.assessment_id,
                    snapshot=snapshot_record,
                    profile_id=assessment.profile_id,
                    profile_version=assessment.profile_version,
                    status=assessment.status,
                    payload=assessment.model_dump(mode="json"),
                    evaluated_at=_dt(assessment.evaluated_at_iso),
                )
                for assessment in assessments
            ]
        )
        ArtifactRecord.objects.bulk_create(
            [
                ArtifactRecord(
                    organization=environment_record.organization,
                    workspace=environment_record.workspace,
                    artifact_id=artifact.artifact_id,
                    scope_type=artifact.scope_type,
                    scope_id=artifact.scope_id,
                    artifact_type=artifact.artifact_type,
                    content_hash=artifact.payload_hash,
                    media_type=artifact.media_type,
                    storage_path=str(paths[artifact.artifact_id]),
                    derived_from=artifact.derived_from,
                    metadata=artifact.metadata,
                )
                for artifact in artifacts
            ]
        )
    return snapshot_record, [
        {"artifact_id": artifact.artifact_id, "artifact_type": artifact.artifact_type, "content_hash": artifact.payload_hash}
        for artifact in artifacts
    ]



def _persist_incident(
    snapshot_record: EnvironmentSnapshotRecord,
    incident: IncidentInvestigation,
) -> tuple[IncidentRecord, list[dict[str, str]]]:
    artifacts = build_incident_artifacts(incident)
    paths = {artifact.artifact_id: artifact_store().put(artifact) for artifact in artifacts}
    certificate = incident.certificate
    with transaction.atomic():
        record, _ = IncidentRecord.objects.update_or_create(
            incident_id=incident.incident_id,
            defaults={
                "environment": snapshot_record.environment,
                "snapshot": snapshot_record,
                "profile_id": incident.profile_id,
                "title": incident.title,
                "initial_symptom": incident.initial_symptom,
                "status": incident.status,
                "certificate_status": certificate.status if certificate else None,
                "confidence": certificate.confidence if certificate else 0.0,
                "payload": incident.model_dump(mode="json"),
                "created_at": _dt(incident.created_at_iso),
                "updated_at": _dt(incident.updated_at_iso),
            },
        )
        record.evidence_facts.all().delete()
        record.hypotheses.all().delete()
        record.probe_runs.all().delete()
        record.timeline_entries.all().delete()
        DiagnosisCertificateRecord.objects.filter(incident=record).delete()
        EvidenceFactRecord.objects.bulk_create(
            [
                EvidenceFactRecord(
                    evidence_id=item.evidence_id,
                    incident=record,
                    fact_type=item.fact_type,
                    collector_id=item.collector_id,
                    authority=item.authority,
                    subject_ids=item.subject_ids,
                    observed_at=_dt(item.observed_at_iso),
                    payload=item.model_dump(mode="json"),
                )
                for item in incident.evidence
            ],
            ignore_conflicts=True,
        )
        HypothesisRecord.objects.bulk_create(
            [
                HypothesisRecord(
                    hypothesis_id=item.hypothesis_id,
                    incident=record,
                    family_id=item.family_id,
                    status=item.status,
                    confidence=item.confidence,
                    subject_ids=item.subject_ids,
                    payload=item.model_dump(mode="json"),
                )
                for item in incident.hypotheses
            ],
            ignore_conflicts=True,
        )
        ProbeRunRecord.objects.bulk_create(
            [
                ProbeRunRecord(
                    probe_run_id=item.probe_run_id,
                    incident=record,
                    probe_id=item.probe.probe_id,
                    intent_id=item.probe.evidence_intent_id,
                    status=item.status,
                    started_at=_dt(item.started_at_iso),
                    completed_at=_dt(item.completed_at_iso),
                    payload=item.model_dump(mode="json"),
                )
                for item in incident.probe_runs
            ],
            ignore_conflicts=True,
        )
        IncidentTimelineRecord.objects.bulk_create(
            [
                IncidentTimelineRecord(
                    incident=record,
                    sequence=item.sequence,
                    event_type=item.event_type,
                    occurred_at=_dt(item.occurred_at_iso),
                    payload=item.model_dump(mode="json"),
                )
                for item in incident.timeline
            ]
        )
        if certificate is not None:
            DiagnosisCertificateRecord.objects.create(
                certificate_id=certificate.certificate_id,
                incident=record,
                status=certificate.status,
                confidence=certificate.confidence,
                issued_at=_dt(certificate.issued_at_iso) if certificate.issued_at_iso else None,
                payload=certificate.model_dump(mode="json"),
            )
        ArtifactRecord.objects.filter(scope_type="incident", scope_id=incident.incident_id).delete()
        ArtifactRecord.objects.bulk_create(
            [
                ArtifactRecord(
                    organization=snapshot_record.environment.organization,
                    workspace=snapshot_record.environment.workspace,
                    artifact_id=artifact.artifact_id,
                    scope_type=artifact.scope_type,
                    scope_id=artifact.scope_id,
                    artifact_type=artifact.artifact_type,
                    content_hash=artifact.payload_hash,
                    media_type=artifact.media_type,
                    storage_path=str(paths[artifact.artifact_id]),
                    derived_from=artifact.derived_from,
                    metadata=artifact.metadata,
                )
                for artifact in artifacts
            ],
            ignore_conflicts=True,
        )
    return record, [
        {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "content_hash": artifact.payload_hash,
        }
        for artifact in artifacts
    ]


def _incident_summary(record: IncidentRecord) -> dict[str, Any]:
    payload = record.payload
    probe_plan = payload.get("probe_plan") or {}
    return {
        "incident_id": record.incident_id,
        "environment_id": record.environment.environment_id,
        "snapshot_id": record.snapshot.snapshot_id,
        "profile_id": record.profile_id,
        "title": record.title,
        "initial_symptom": record.initial_symptom,
        "status": record.status,
        "certificate_status": record.certificate_status,
        "confidence": record.confidence,
        "symptom_count": len(payload.get("symptoms", [])),
        "evidence_count": len(payload.get("evidence", [])),
        "hypothesis_count": len(payload.get("hypotheses", [])),
        "recommended_probe_count": len(probe_plan.get("probes", [])),
        "updated_at": record.updated_at,
    }

def _environment_summary(record: EnvironmentRecord) -> dict[str, Any]:
    latest_snapshot = record.snapshots.first()
    latest_validation = record.access_validations.first()
    assessments = list(latest_snapshot.assessments.all()) if latest_snapshot else []
    return {
        "environment_id": record.environment_id,
        "name": record.name,
        "environment_class": record.environment_class,
        "provider": record.provider,
        "cluster_provider": record.cluster_provider,
        "host_provider": record.host_provider,
        "criticality": record.criticality,
        "fingerprint": record.fingerprint,
        "active": record.active,
        "updated_at": record.updated_at,
        "latest_validation": latest_validation.payload if latest_validation else None,
        "latest_snapshot": _snapshot_summary(latest_snapshot) if latest_snapshot else None,
        "latest_health": [item.payload for item in assessments],
    }


def _snapshot_summary(record: EnvironmentSnapshotRecord) -> dict[str, Any]:
    return {
        "snapshot_id": record.snapshot_id,
        "environment_id": record.environment.environment_id,
        "status": record.status,
        "source_type": record.source_type,
        "source_fingerprint": record.source_fingerprint,
        "captured_at_iso": record.captured_at,
        "content_hash": record.content_hash,
        "summary": record.summary,
        "entity_count": record.entities.count(),
        "relationship_count": record.relationships.count(),
        "assessment_count": record.assessments.count(),
    }



class KnowledgePackListView(APIView):
    def get(self, request: Request) -> Response:
        manager = pack_manager()
        _, workspace_id = requested_scope(request)
        runtime = pack_runtime_for_workspace(workspace_id)
        resolution = runtime.resolution
        status_by_id = {item.pack_id: item for item in resolution.statuses}
        payload = []
        for manifest in manager.values():
            status_item = status_by_id.get(manifest.pack_id)
            payload.append({
                "manifest": manifest.model_dump(mode="json"),
                "source": manager.source(manifest.pack_id),
                "status": status_item.model_dump(mode="json") if status_item else None,
            })
        return Response({
            "packs": payload,
            "resolution": resolution.model_dump(mode="json"),
            "coverage": runtime.coverage_report().model_dump(mode="json"),
        })


class KnowledgePackDetailView(APIView):
    def get(self, request: Request, pack_id: str) -> Response:
        try:
            manifest = pack_manager().get(pack_id)
            _, workspace_id = requested_scope(request)
            runtime = resolve_pack_runtime_for_workspace(workspace_id, (pack_id,))
        except KeyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response({
            "manifest": manifest.model_dump(mode="json"),
            "source": pack_manager().source(pack_id),
            "resolution": runtime.resolution.model_dump(mode="json"),
            "issues": [item.model_dump(mode="json") for item in pack_manager().validate(pack_id)],
        })


class KnowledgePackResolveView(APIView):
    def post(self, request: Request) -> Response:
        requested = request.data.get("pack_ids")
        try:
            _, workspace_id = requested_scope(request)
            requested_ids = tuple(requested) if requested else None
            runtime = resolve_pack_runtime_for_workspace(workspace_id, requested_ids)
        except (KeyError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(runtime.resolution.model_dump(mode="json"))


class KnowledgePackCoverageView(APIView):
    def get(self, request: Request) -> Response:
        _, workspace_id = requested_scope(request)
        return Response(pack_runtime_for_workspace(workspace_id).coverage_report().model_dump(mode="json"))


class SystemStatusView(APIView):
    public_access = True

    def get(self, request: Request) -> Response:
        return Response(
            {
                "service": "kubeops-control-plane",
                "release": "1.0.0",
                "core_version": core_version,
                "mode": "production_control_plane",
                "status": "ok",
                "anonymous_read_enabled": settings.KUBEOPS_ALLOW_ANONYMOUS_READ,
                "family_count": len(scenario_registry()),
                "pack_count": len(pack_manager().values()),
                "active_pack_count": len(pack_runtime().active_pack_ids),
                "profile_count": len(profile_registry()),
                "environment_count": EnvironmentRecord.objects.filter(active=True).count(),
                "incident_count": IncidentRecord.objects.count(),
                "diagnostic_intent_count": len(diagnostic_catalog().intents()),
                "diagnostic_collector_count": len(diagnostic_catalog().collectors()),
                "causal_template_count": len(diagnostic_catalog().templates()),
                "action_type_count": len(action_catalog()),
                "lifecycle_profile_count": len(lifecycle_registry()),
                "execution_policy_count": len(policy_registry()),
                "operation_count": OperationRecord.objects.count(),
                "organization_count": OrganizationRecord.objects.count(),
                "workspace_count": WorkspaceRecord.objects.count(),
                "fleet_count": FleetRecord.objects.count(),
                "executor_count": ExecutorAgentRecord.objects.count(),
                "capabilities": [
                    "canonical_ir",
                    "scenario_compilation",
                    "deterministic_simulation",
                    "environment_registry",
                    "read_only_access_validation",
                    "fixture_replay",
                    "kubectl_discovery",
                    "secret_redaction",
                    "immutable_snapshots",
                    "snapshot_diff",
                    "topology_compilation",
                    "graph_invariants",
                    "operational_profiles",
                    "temporal_health",
                    "artifact_persistence",
                    "evidence_intents",
                    "collector_planning",
                    "normalized_evidence",
                    "deterministic_hypotheses",
                    "contradiction_analysis",
                    "parent_family_fallback",
                    "probe_planning",
                    "diagnosis_certificates",
                    "incident_persistence",
                    "lifecycle_planning",
                    "typed_actions",
                    "independent_policy_decisions",
                    "approval_gates",
                    "durable_execution",
                    "idempotency_guards",
                    "execution_checkpoints",
                    "rollback",
                    "semantic_verification",
                    "recovery_certificates",
                    "knowledge_packs",
                    "pack_dependency_resolution",
                    "pack_compatibility_validation",
                    "provider_pack_specialization",
                    "component_pack_specialization",
                    "pack_redaction",
                    "pack_scenario_coverage",
                    "pack_authoring_sdk",
                    "multi_tenant_rbac",
                    "fleet_intelligence",
                    "common_cause_detection",
                    "distributed_executor_leases",
                    "tamper_evident_audit",
                    "retention_planning",
                    "secret_references",
                    "pack_signature_verification",
                    "platform_backup_restore",
                    "upgrade_readiness",
                ],
            }
        )


class RegistryView(APIView):
    def get(self, request: Request) -> Response:
        _, workspace_id = requested_scope(request)
        payload = registry_catalog_for_workspace(workspace_id).snapshot().model_dump(mode="json")
        payload["schemas"] = sorted(SchemaView.schema_types)
        return Response(payload)


class SchemaView(APIView):
    schema_types = {
        model.__name__: model
        for model in [
            OperationalEntity, Relationship, OperationalObjective, OperationalProfile,
            InvariantDefinition, Observation, ObservationProfile,
            EvidenceIntent, CollectorDefinition, EvidenceFact, EvidenceCollectionPlan,
            CollectorRunResult, Symptom, CausalTemplate, CausalEdge, Hypothesis,
            ProbeIntent, ProbePlan, ProbeRun, IncidentTimelineEntry, IncidentInvestigation,
            DiagnosticExpectation, DiagnosticCaseResult, DiagnosticEvaluationReport,
            DiagnosisCertificate, ScenarioFamily, ScenarioInstance, ScenarioComposition,
            ActionTypeDefinition, ActionInstance, ExecutionPolicy, PolicyDecision, RecoveryPlan,
            VerificationCondition, VerificationResult, RecoveryCertificate, SimulationRun,
            LifecycleProfile, ApprovalRecord, ActionReceipt, ExecutionCheckpoint, OperationEvent, OperationRun,
            RunArtifact, OperationalArtifact, AccessMethodDefinition, EnvironmentDefinition,
            AccessValidationResult, DiscoveryBundle, EnvironmentSnapshot, SnapshotDiff,
            TopologyGraph, OperationalProfileSpec, CompiledOperationalProfile,
            OperationalProfileAssessment, KnowledgePackManifest, PackCompatibility,
            PackContributions, PackCoverageReport, PackDependency, PackResolution,
            PackScenarioCoverage, PackStatus, PackValidationIssue, EntityClassifierRule,
            RelationshipResolverRule, RedactionRule,
            OrganizationDefinition, WorkspaceDefinition, RoleGrant, AuthorizationRequest, AuthorizationDecision, ScopeBinding,
            FleetMember, FleetDependency, FleetDefinition, FleetEnvironmentStatus, CommonCauseFinding, FleetAssessment, FleetOperationWave, FleetOperationPlan,
            ExecutorAgentDefinition, ExecutorHeartbeat, ExecutionTask, TaskLease, DispatchDecision,
            RateLimitRule, ConcurrencyRule, GovernanceDecision, RetentionPolicy, RetentionCandidate, RetentionPlan,
            AuditEvent, AuditChainVerification, AuditExport, SecretReference, SecretResolutionReceipt,
            PackSignature, PackTrustPolicy, PackVerificationResult, BackupComponent, ControlPlaneBackupManifest,
            ControlPlaneRestorePlan, RestoreStep, UpgradeReadinessCheck, UpgradeReadinessReport,
            MaintenanceWindow, ScheduledOperation, ScheduleDecision,
        ]
    }

    def get(self, request: Request, schema_name: str) -> Response:
        model = self.schema_types.get(schema_name)
        if model is None:
            return Response({"detail": "schema not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(model.model_json_schema())


class OperationalProfileListView(APIView):
    def get(self, request: Request) -> Response:
        payload = []
        _, workspace_id = requested_scope(request)
        for profile in profile_registry_for_workspace(workspace_id).values():
            item = profile.model_dump(mode="json")
            item["content_hash"] = profile.content_hash
            payload.append(item)
        return Response(payload)


class OperationalProfileDetailView(APIView):
    def get(self, request: Request, profile_id: str) -> Response:
        try:
            _, workspace_id = requested_scope(request)
            profile = profile_registry_for_workspace(workspace_id).get(profile_id)
        except KeyError:
            return Response({"detail": "operational profile not found"}, status=status.HTTP_404_NOT_FOUND)
        payload = profile.model_dump(mode="json")
        payload["content_hash"] = profile.content_hash
        return Response(payload)


class EnvironmentListView(APIView):
    def get(self, request: Request) -> Response:
        _, workspace_id = requested_scope(request)
        records = (
            EnvironmentRecord.objects.prefetch_related("snapshots__assessments", "access_validations")
            .filter(active=True, workspace__workspace_id=workspace_id)
        )
        return Response([_environment_summary(record) for record in records])

    def post(self, request: Request) -> Response:
        try:
            environment = EnvironmentDefinition.model_validate(request.data)
            enforce_payload_scope(
                request, organization_id=environment.organization_id, workspace_id=environment.workspace_id
            )
        except ValidationError as exc:
            return _validation_error(exc)
        if EnvironmentRecord.objects.filter(environment_id=environment.environment_id).exists():
            return Response({"detail": "environment already exists"}, status=status.HTTP_409_CONFLICT)
        record = _persist_environment(environment)
        return Response(_environment_summary(record), status=status.HTTP_201_CREATED)


class EnvironmentDetailView(APIView):
    def get(self, request: Request, environment_id: str) -> Response:
        record = get_object_or_404(EnvironmentRecord, environment_id=environment_id, active=True)
        payload = _environment(record).model_dump(mode="json")
        payload["fingerprint"] = record.fingerprint
        payload["latest_validation"] = record.access_validations.first().payload if record.access_validations.exists() else None
        payload["snapshots"] = [_snapshot_summary(item) for item in record.snapshots.all()[:50]]
        return Response(payload)

    def put(self, request: Request, environment_id: str) -> Response:
        if request.data.get("environment_id", environment_id) != environment_id:
            return Response({"detail": "environment_id cannot be changed"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        payload = dict(request.data)
        payload["environment_id"] = environment_id
        try:
            environment = EnvironmentDefinition.model_validate(payload)
            enforce_payload_scope(
                request, organization_id=environment.organization_id, workspace_id=environment.workspace_id
            )
        except ValidationError as exc:
            return _validation_error(exc)
        record = _persist_environment(environment, update=True)
        return Response(_environment_summary(record))

    def delete(self, request: Request, environment_id: str) -> Response:
        record = get_object_or_404(EnvironmentRecord, environment_id=environment_id)
        record.active = False
        record.save(update_fields=["active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class EnvironmentAccessValidationView(APIView):
    def post(self, request: Request, environment_id: str) -> Response:
        record = get_object_or_404(EnvironmentRecord, environment_id=environment_id, active=True)
        try:
            workspace_id = _record_workspace_id(record)
            result = environment_intelligence_for_workspace(workspace_id).validate(
                _environment(record), request.data.get("method_id")
            )
        except (OSError, ValueError, TimeoutError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        _persist_validation(record, result)
        return Response(result.model_dump(mode="json"), status=status.HTTP_201_CREATED)


class EnvironmentSnapshotListView(APIView):
    def get(self, request: Request, environment_id: str) -> Response:
        record = get_object_or_404(EnvironmentRecord, environment_id=environment_id, active=True)
        return Response([_snapshot_summary(item) for item in record.snapshots.all()[:100]])

    def post(self, request: Request, environment_id: str) -> Response:
        record = get_object_or_404(EnvironmentRecord, environment_id=environment_id, active=True)
        environment = _environment(record)
        profile_ids = request.data.get("profile_ids") or environment.operational_profile_ids
        try:
            workspace_id = _record_workspace_id(record)
            profiles = [profile_registry_for_workspace(workspace_id).get(profile_id) for profile_id in profile_ids]
        except KeyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        history_records = list(record.snapshots.all()[:20])
        history = [_snapshot(item) for item in reversed(history_records)]
        previous = history[-1] if history else None
        try:
            result = environment_intelligence_for_workspace(workspace_id).collect(
                environment,
                method_id=request.data.get("method_id"),
                resource_types=request.data.get("resource_types"),
                profiles=profiles,
                history=history,
            )
        except (OSError, ValueError, TimeoutError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        snapshot_diff = diff_snapshots(previous, result.snapshot) if previous else None
        snapshot_record, artifacts = _persist_snapshot(
            record,
            result.bundle,
            result.snapshot,
            result.topology,
            result.assessments,
            snapshot_diff,
        )
        payload = result.snapshot.model_dump(mode="json")
        payload["topology"] = result.topology.model_dump(mode="json")
        payload["assessments"] = [item.model_dump(mode="json") for item in result.assessments]
        payload["diff_from_previous"] = snapshot_diff.model_dump(mode="json") if snapshot_diff else None
        payload["artifacts"] = artifacts
        payload["record"] = _snapshot_summary(snapshot_record)
        return Response(payload, status=status.HTTP_201_CREATED)


class SnapshotDetailView(APIView):
    def get(self, request: Request, snapshot_id: str) -> Response:
        record = get_object_or_404(EnvironmentSnapshotRecord.objects.select_related("environment"), snapshot_id=snapshot_id)
        payload = dict(record.payload)
        payload["assessments"] = [item.payload for item in record.assessments.all()]
        payload["artifacts"] = [
            {
                "artifact_id": artifact.artifact_id,
                "artifact_type": artifact.artifact_type,
                "content_hash": artifact.content_hash,
                "metadata": artifact.metadata,
            }
            for artifact in ArtifactRecord.objects.filter(scope_type="environment_snapshot", scope_id=snapshot_id)
        ]
        return Response(payload)


class SnapshotTopologyView(APIView):
    def get(self, request: Request, snapshot_id: str) -> Response:
        record = get_object_or_404(EnvironmentSnapshotRecord, snapshot_id=snapshot_id)
        topology = TopologyCompiler().compile_snapshot(_snapshot(record))
        return Response(topology.model_dump(mode="json"))


class SnapshotDiffView(APIView):
    def get(self, request: Request, snapshot_id: str) -> Response:
        after_record = get_object_or_404(EnvironmentSnapshotRecord, snapshot_id=snapshot_id)
        before_id = request.query_params.get("before")
        if before_id:
            before_record = get_object_or_404(EnvironmentSnapshotRecord, snapshot_id=before_id, environment=after_record.environment)
        else:
            before_record = after_record.environment.snapshots.filter(captured_at__lt=after_record.captured_at).first()
            if before_record is None:
                return Response({"detail": "no prior snapshot exists"}, status=status.HTTP_404_NOT_FOUND)
        result = diff_snapshots(_snapshot(before_record), _snapshot(after_record))
        return Response(result.model_dump(mode="json"))


class SnapshotHealthView(APIView):
    def get(self, request: Request, snapshot_id: str) -> Response:
        record = get_object_or_404(EnvironmentSnapshotRecord.objects.select_related("environment"), snapshot_id=snapshot_id)
        profile_id = request.query_params.get("profile_id")
        if not profile_id:
            return Response([item.payload for item in record.assessments.all()])
        existing = record.assessments.filter(profile_id=profile_id).first()
        if existing:
            return Response(existing.payload)
        try:
            workspace_id = _record_workspace_id(record.environment)
            profile = profile_registry_for_workspace(workspace_id).get(profile_id)
        except KeyError:
            return Response({"detail": "operational profile not found"}, status=status.HTTP_404_NOT_FOUND)
        history_records = list(record.environment.snapshots.filter(captured_at__lte=record.captured_at).order_by("captured_at"))
        assessment = HealthAssessmentEngine().assess(profile, _snapshot(record), [_snapshot(item) for item in history_records])
        ProfileAssessmentRecord.objects.create(
            assessment_id=assessment.assessment_id,
            snapshot=record,
            profile_id=assessment.profile_id,
            profile_version=assessment.profile_version,
            status=assessment.status,
            payload=assessment.model_dump(mode="json"),
            evaluated_at=_dt(assessment.evaluated_at_iso),
        )
        return Response(assessment.model_dump(mode="json"), status=status.HTTP_201_CREATED)


class SnapshotFixtureExportView(APIView):
    def get(self, request: Request, snapshot_id: str) -> Response:
        record = get_object_or_404(
            ArtifactRecord,
    DiagnosisCertificateRecord,
    EvidenceFactRecord,
            scope_type="environment_snapshot",
            scope_id=snapshot_id,
            artifact_type="raw_discovery_bundle",
        )
        artifact = artifact_store().get(record.scope_id, record.artifact_id)
        bundle = DiscoveryBundle.model_validate(artifact.payload)
        return Response(export_discovery_fixture(bundle, snapshot_id=snapshot_id))


class DiagnosticCatalogView(APIView):
    def get(self, request: Request) -> Response:
        _, workspace_id = requested_scope(request)
        catalog = diagnostic_catalog_for_workspace(workspace_id)
        return Response(
            {
                "intents": [item.model_dump(mode="json") for item in catalog.intents()],
                "collectors": [item.model_dump(mode="json") for item in catalog.collectors()],
                "causal_templates": [item.model_dump(mode="json") for item in catalog.templates()],
                "counts": {
                    "intents": len(catalog.intents()),
                    "collectors": len(catalog.collectors()),
                    "causal_templates": len(catalog.templates()),
                },
                "read_only": all(item.risk_class == "R0" for item in catalog.collectors()),
            }
        )


class IncidentListView(APIView):
    def get(self, request: Request) -> Response:
        _, workspace_id = requested_scope(request)
        queryset = IncidentRecord.objects.select_related("environment", "snapshot").filter(
            environment__workspace__workspace_id=workspace_id
        )
        environment_id = request.query_params.get("environment_id")
        incident_status = request.query_params.get("status")
        if environment_id:
            queryset = queryset.filter(environment__environment_id=environment_id)
        if incident_status:
            queryset = queryset.filter(status=incident_status)
        return Response([_incident_summary(record) for record in queryset[:250]])


class SnapshotIncidentCreateView(APIView):
    def post(self, request: Request, snapshot_id: str) -> Response:
        snapshot_record = get_object_or_404(
            EnvironmentSnapshotRecord.objects.select_related("environment"),
            snapshot_id=snapshot_id,
        )
        profile_id = request.data.get("profile_id")
        if not profile_id:
            return Response({"detail": "profile_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            workspace_id = _record_workspace_id(snapshot_record.environment)
            profile = profile_registry_for_workspace(workspace_id).get(profile_id)
        except KeyError:
            return Response({"detail": "operational profile not found"}, status=status.HTTP_404_NOT_FOUND)
        snapshot = _snapshot(snapshot_record)
        topology = TopologyCompiler().compile_snapshot(snapshot)
        history_records = list(
            snapshot_record.environment.snapshots.filter(captured_at__lte=snapshot_record.captured_at).order_by("captured_at")
        )
        incident = investigation_service_for_workspace(workspace_id).open(
            snapshot,
            profile,
            topology=topology,
            history=[_snapshot(item) for item in history_records],
            title=request.data.get("title"),
            initial_symptom=request.data.get("initial_symptom"),
            evidence_budget=request.data.get("evidence_budget", 5),
        )
        _, artifacts = _persist_incident(snapshot_record, incident)
        payload = incident.model_dump(mode="json")
        payload["artifacts"] = artifacts
        return Response(payload, status=status.HTTP_201_CREATED)


class IncidentDetailView(APIView):
    def get(self, request: Request, incident_id: str) -> Response:
        record = get_object_or_404(
            IncidentRecord.objects.select_related("environment", "snapshot"),
            incident_id=incident_id,
        )
        payload = dict(record.payload)
        payload["artifacts"] = [
            {
                "artifact_id": artifact.artifact_id,
                "artifact_type": artifact.artifact_type,
                "content_hash": artifact.content_hash,
                "derived_from": artifact.derived_from,
            }
            for artifact in ArtifactRecord.objects.filter(scope_type="incident", scope_id=incident_id)
        ]
        return Response(payload)


class IncidentProbeRunView(APIView):
    def post(self, request: Request, incident_id: str, probe_id: str) -> Response:
        record = get_object_or_404(
            IncidentRecord.objects.select_related("environment", "snapshot"),
            incident_id=incident_id,
        )
        incident = IncidentInvestigation.model_validate(record.payload)
        try:
            workspace_id = _record_workspace_id(record.environment)
            profile = profile_registry_for_workspace(workspace_id).get(incident.profile_id)
        except KeyError:
            return Response({"detail": "operational profile not found"}, status=status.HTTP_404_NOT_FOUND)
        snapshot = _snapshot(record.snapshot)
        topology = TopologyCompiler().compile_snapshot(snapshot)
        history_records = list(
            record.environment.snapshots.filter(captured_at__lte=record.snapshot.captured_at).order_by("captured_at")
        )
        try:
            refined = investigation_service_for_workspace(workspace_id).run_probe(
                incident,
                probe_id,
                snapshot,
                profile,
                topology=topology,
                history=[_snapshot(item) for item in history_records],
                evidence_budget=request.data.get("evidence_budget", 5),
            )
        except KeyError:
            return Response({"detail": "probe not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        _, artifacts = _persist_incident(record.snapshot, refined)
        payload = refined.model_dump(mode="json")
        payload["artifacts"] = artifacts
        return Response(payload, status=status.HTTP_201_CREATED)


class IncidentCertificateView(APIView):
    def get(self, request: Request, incident_id: str) -> Response:
        record = get_object_or_404(IncidentRecord, incident_id=incident_id)
        if not record.payload.get("certificate"):
            return Response({"detail": "diagnosis certificate not available"}, status=status.HTTP_404_NOT_FOUND)
        return Response(record.payload["certificate"])


class DiagnosisCoverageView(APIView):
    def get(self, request: Request) -> Response:
        incidents = list(IncidentRecord.objects.all())
        hypotheses = list(HypothesisRecord.objects.all())
        family_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for hypothesis in hypotheses:
            family_counts[hypothesis.family_id] = family_counts.get(hypothesis.family_id, 0) + 1
        for incident in incidents:
            key = incident.certificate_status or "none"
            status_counts[key] = status_counts.get(key, 0) + 1
        _, workspace_id = requested_scope(request)
        catalog = diagnostic_catalog_for_workspace(workspace_id)
        represented = {item.family_id for item in catalog.templates() if not item.generic}
        observed = set(family_counts)
        return Response(
            {
                "incident_count": len(incidents),
                "hypothesis_count": len(hypotheses),
                "certificate_status_counts": dict(sorted(status_counts.items())),
                "observed_family_counts": dict(sorted(family_counts.items())),
                "catalog_family_count": len(represented),
                "observed_catalog_families": sorted(represented & observed),
                "unobserved_catalog_families": sorted(represented - observed),
                "collector_count": len(catalog.collectors()),
                "all_collectors_read_only": all(item.risk_class == "R0" for item in catalog.collectors()),
            }
        )


# Release 0.1 scenario laboratory endpoints remain stable.
class ScenarioFamilyListView(APIView):
    def get(self, request: Request) -> Response:
        payload = []
        compiler = scenario_compiler()
        for family in scenario_registry().values():
            effective = compiler.effective_family(family.family_id)
            item = effective.model_dump(mode="json")
            item["content_hash"] = effective.content_hash
            item["lineage"] = [node.family_id for node in scenario_registry().lineage(family.family_id)]
            payload.append(item)
        return Response(payload)


class ScenarioFamilyDetailView(APIView):
    def get(self, request: Request, family_id: str) -> Response:
        family = scenario_registry().maybe_get(family_id)
        if family is None:
            return Response({"detail": "scenario family not found"}, status=status.HTTP_404_NOT_FOUND)
        effective = scenario_compiler().effective_family(family_id)
        payload = effective.model_dump(mode="json")
        payload["content_hash"] = effective.content_hash
        payload["lineage"] = [node.family_id for node in scenario_registry().lineage(family_id)]
        return Response(payload)


class ScenarioCompileView(APIView):
    def post(self, request: Request) -> Response:
        payload = request.data
        try:
            scenario = scenario_compiler().compile(
                payload["family_id"],
                payload.get("bindings", {}),
                disturbance_id=payload.get("disturbance_id"),
                observation_profile_id=payload.get("observation_profile_id"),
                scenario_id=payload.get("scenario_id"),
                max_time_seconds=int(payload.get("max_time_seconds", 20)),
            )
        except KeyError as exc:
            return Response({"errors": [f"missing field {exc.args[0]}"]}, status=status.HTTP_400_BAD_REQUEST)
        except (ScenarioCompileError, ValueError) as exc:
            return Response({"errors": getattr(exc, "errors", [str(exc)])}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(scenario.model_dump(mode="json"), status=status.HTTP_201_CREATED)


class ScenarioDiagnoseView(APIView):
    """Compile, simulate, and diagnose a scenario using the read-only Release 0.3 pipeline."""

    def post(self, request: Request) -> Response:
        payload = request.data
        try:
            scenario = scenario_compiler().compile(
                payload["family_id"],
                payload.get("bindings", {}),
                disturbance_id=payload.get("disturbance_id"),
                observation_profile_id=payload.get("observation_profile_id"),
                scenario_id=payload.get("scenario_id"),
                max_time_seconds=int(payload.get("max_time_seconds", 20)),
            )
            expectation = DiagnosticExpectation.model_validate(payload.get("expectation", {}))
        except KeyError as exc:
            return Response({"errors": [f"missing field {exc.args[0]}"]}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as exc:
            return _validation_error(exc)
        except (ScenarioCompileError, ValueError) as exc:
            return Response({"errors": getattr(exc, "errors", [str(exc)])}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        run = simulation_engine().run(scenario, seed=int(payload.get("seed", 0)))
        _, workspace_id = requested_scope(request)
        result = scenario_diagnosis_evaluator_for_workspace(workspace_id).evaluate(scenario, run, expectation)
        response = result.model_dump(mode="json")
        response["run"] = run.model_dump(mode="json")
        response["scenario"] = scenario.model_dump(mode="json")
        organization, workspace = _request_scope_records(request)
        response["artifacts"] = _persist_run(scenario, run, organization, workspace)
        return Response(response, status=status.HTTP_201_CREATED)


class ScenarioRunView(APIView):
    def post(self, request: Request) -> Response:
        payload = request.data
        try:
            scenario = scenario_compiler().compile(
                payload["family_id"],
                payload.get("bindings", {}),
                disturbance_id=payload.get("disturbance_id"),
                observation_profile_id=payload.get("observation_profile_id"),
                scenario_id=payload.get("scenario_id"),
                max_time_seconds=int(payload.get("max_time_seconds", 20)),
            )
        except KeyError as exc:
            return Response({"errors": [f"missing field {exc.args[0]}"]}, status=status.HTTP_400_BAD_REQUEST)
        except (ScenarioCompileError, ValueError) as exc:
            return Response({"errors": getattr(exc, "errors", [str(exc)])}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        run = simulation_engine().run(scenario, seed=int(payload.get("seed", 0)))
        response = run.model_dump(mode="json")
        response["scenario"] = scenario.model_dump(mode="json")
        organization, workspace = _request_scope_records(request)
        response["artifacts"] = _persist_run(scenario, run, organization, workspace)
        return Response(response, status=status.HTTP_201_CREATED)


class CompositionCompileView(APIView):
    def post(self, request: Request) -> Response:
        try:
            spec = ScenarioComposition.model_validate(request.data)
            scenario = ScenarioComposer(scenario_compiler()).compose(spec)
        except (ValidationError, ValueError, ScenarioCompileError) as exc:
            errors = [item.get("msg", str(item)) for item in exc.errors()] if isinstance(exc, ValidationError) else getattr(exc, "errors", [str(exc)])
            return Response({"errors": errors}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(scenario.model_dump(mode="json"), status=status.HTTP_201_CREATED)


class CompositionRunView(APIView):
    def post(self, request: Request) -> Response:
        try:
            spec = ScenarioComposition.model_validate(request.data)
            scenario = ScenarioComposer(scenario_compiler()).compose(spec)
        except (ValidationError, ValueError, ScenarioCompileError) as exc:
            errors = [item.get("msg", str(item)) for item in exc.errors()] if isinstance(exc, ValidationError) else getattr(exc, "errors", [str(exc)])
            return Response({"errors": errors}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        run = simulation_engine().run(scenario, seed=int(request.data.get("seed", 0)))
        response = run.model_dump(mode="json")
        response["scenario"] = scenario.model_dump(mode="json")
        organization, workspace = _request_scope_records(request)
        response["artifacts"] = _persist_run(scenario, run, organization, workspace)
        return Response(response, status=status.HTTP_201_CREATED)


class ArtifactListView(APIView):
    def get(self, request: Request) -> Response:
        _, workspace_id = requested_scope(request)
        queryset = ArtifactRecord.objects.select_related("run").filter(workspace__workspace_id=workspace_id)
        run_id = request.query_params.get("run_id")
        scope_id = request.query_params.get("scope_id")
        scope_type = request.query_params.get("scope_type")
        if run_id:
            queryset = queryset.filter(run__run_id=run_id)
        if scope_id:
            queryset = queryset.filter(scope_id=scope_id)
        if scope_type:
            queryset = queryset.filter(scope_type=scope_type)
        return Response(
            [
                {
                    "artifact_id": artifact.artifact_id,
                    "run_id": artifact.run.run_id if artifact.run else None,
                    "scope_type": artifact.scope_type,
                    "scope_id": artifact.scope_id,
                    "artifact_type": artifact.artifact_type,
                    "content_hash": artifact.content_hash,
                    "media_type": artifact.media_type,
                    "derived_from": artifact.derived_from,
                    "metadata": artifact.metadata,
                    "created_at": artifact.created_at,
                }
                for artifact in queryset[:500]
            ]
        )


class ArtifactDetailView(APIView):
    def get(self, request: Request, artifact_id: str) -> Response:
        _, workspace_id = requested_scope(request)
        record = get_object_or_404(
            ArtifactRecord.objects.select_related("run"), artifact_id=artifact_id, workspace__workspace_id=workspace_id
        )
        scope_id = record.scope_id or (record.run.run_id if record.run else "")
        artifact = artifact_store().get(scope_id, record.artifact_id)
        payload = artifact.model_dump(mode="json")
        payload["content_hash"] = payload.pop("payload_hash")
        return Response(payload)


class ScenarioRunListView(APIView):
    def get(self, request: Request) -> Response:
        _, workspace_id = requested_scope(request)
        return Response(
            [
                {
                    "run_id": record.run_id,
                    "scenario_id": record.scenario_id,
                    "family_id": record.family_id,
                    "status": record.status,
                    "created_at": record.created_at,
                    "completed_at": record.completed_at,
                    "final_summary": record.run_payload.get("final_summary", {}),
                }
                for record in ScenarioRunRecord.objects.filter(workspace__workspace_id=workspace_id)[:100]
            ]
        )


class ScenarioRunDetailView(APIView):
    def get(self, request: Request, run_id: str) -> Response:
        _, workspace_id = requested_scope(request)
        record = get_object_or_404(ScenarioRunRecord, run_id=run_id, workspace__workspace_id=workspace_id)
        payload = dict(record.run_payload)
        payload["scenario"] = record.scenario_payload
        payload["artifacts"] = [
            {
                "artifact_id": artifact.artifact_id,
                "artifact_type": artifact.artifact_type,
                "content_hash": artifact.content_hash,
                "media_type": artifact.media_type,
            }
            for artifact in record.artifacts.all()
        ]
        return Response(payload)


def _operation(record: OperationRecord) -> OperationRun:
    return OperationRun.model_validate(record.payload)


def _operation_summary(record: OperationRecord) -> dict[str, Any]:
    payload = record.payload
    return {
        "operation_id": record.operation_id,
        "environment_id": record.environment.environment_id,
        "snapshot_id": record.snapshot.snapshot_id if record.snapshot else None,
        "incident_id": record.incident.incident_id if record.incident else None,
        "operation_type": record.operation_type,
        "objective_id": record.objective_id,
        "status": record.status,
        "mode": record.mode,
        "plan_id": record.plan_id,
        "policy_id": record.policy_id,
        "certificate_status": record.certificate_status,
        "action_count": len(payload.get("plan", {}).get("actions", [])),
        "receipt_count": len(payload.get("action_receipts", [])),
        "approval_count": len(payload.get("approvals", [])),
        "updated_at": record.updated_at,
    }


def _persist_operation(
    operation: OperationRun,
    environment_record: EnvironmentRecord,
    *,
    snapshot_record: EnvironmentSnapshotRecord | None = None,
    incident_record: IncidentRecord | None = None,
) -> tuple[OperationRecord, list[dict[str, str]]]:
    artifacts = build_operation_artifacts(operation)
    paths = {item.artifact_id: artifact_store().put(item) for item in artifacts}
    with transaction.atomic():
        record, _ = OperationRecord.objects.update_or_create(
            operation_id=operation.operation_id,
            defaults={
                "environment": environment_record,
                "snapshot": snapshot_record,
                "incident": incident_record,
                "operation_type": operation.operation_type,
                "objective_id": operation.objective_id,
                "status": operation.status,
                "mode": operation.mode,
                "plan_id": operation.plan.plan_id,
                "policy_id": operation.plan.policy_id,
                "certificate_status": operation.recovery_certificate.status if operation.recovery_certificate else None,
                "payload": operation.model_dump(mode="json"),
                "created_at": _dt(operation.created_at_iso),
                "updated_at": _dt(operation.updated_at_iso),
                "started_at": _dt(operation.started_at_iso) if operation.started_at_iso else None,
                "completed_at": _dt(operation.completed_at_iso) if operation.completed_at_iso else None,
            },
        )
        for related in [
            OperationPolicyDecisionRecord,
            OperationApprovalRecord,
            ActionReceiptRecord,
            OperationTimelineRecord,
            ExecutionCheckpointRecord,
            OperationVerificationRecord,
            RecoveryCertificateRecord,
        ]:
            related.objects.filter(operation=record).delete()
        OperationPolicyDecisionRecord.objects.bulk_create([
            OperationPolicyDecisionRecord(decision_id=item.decision_id, operation=record, action_id=item.action_id, policy_id=item.policy_id, outcome=item.outcome, payload=item.model_dump(mode="json"))
            for item in operation.policy_decisions
        ])
        OperationApprovalRecord.objects.bulk_create([
            OperationApprovalRecord(approval_id=item.approval_id, operation=record, action_id=item.action_id, approver_id=item.approver_id, decision=item.decision, granted_at=_dt(item.granted_at_iso), payload=item.model_dump(mode="json"))
            for item in operation.approvals
        ])
        ActionReceiptRecord.objects.bulk_create([
            ActionReceiptRecord(receipt_id=item.receipt_id, operation=record, action_id=item.action_id, action_type_id=item.action_type_id, executor_id=item.executor_id, status=item.status, attempt=item.attempt, started_at=_dt(item.started_at_iso), completed_at=_dt(item.completed_at_iso), idempotency_key=item.idempotency_key, payload=item.model_dump(mode="json"))
            for item in operation.action_receipts
        ])
        OperationTimelineRecord.objects.bulk_create([
            OperationTimelineRecord(operation=record, sequence=item.sequence, event_type=item.event_type, action_id=item.action_id, occurred_at=_dt(item.occurred_at_iso), payload=item.model_dump(mode="json"))
            for item in operation.events
        ])
        ExecutionCheckpointRecord.objects.bulk_create([
            ExecutionCheckpointRecord(checkpoint_id=item.checkpoint_id, operation=record, state_hash=item.state_hash, resumable=item.resumable, created_at=_dt(item.created_at_iso), payload=item.model_dump(mode="json"))
            for item in operation.checkpoints
        ])
        OperationVerificationRecord.objects.bulk_create([
            OperationVerificationRecord(result_id=item.result_id, operation=record, condition_id=item.condition_id, status=item.status, payload=item.model_dump(mode="json"))
            for item in operation.verification_results
        ])
        if operation.recovery_certificate:
            RecoveryCertificateRecord.objects.create(certificate_id=operation.recovery_certificate.certificate_id, operation=record, status=operation.recovery_certificate.status, payload=operation.recovery_certificate.model_dump(mode="json"))
        ArtifactRecord.objects.filter(scope_type="operation", scope_id=operation.operation_id).delete()
        ArtifactRecord.objects.bulk_create([
            ArtifactRecord(organization=environment_record.organization, workspace=environment_record.workspace, artifact_id=item.artifact_id, scope_type=item.scope_type, scope_id=item.scope_id, artifact_type=item.artifact_type, content_hash=item.payload_hash, media_type=item.media_type, storage_path=str(paths[item.artifact_id]), derived_from=item.derived_from, metadata=item.metadata)
            for item in artifacts
        ], ignore_conflicts=True)
    return record, [{"artifact_id": item.artifact_id, "artifact_type": item.artifact_type, "content_hash": item.payload_hash} for item in artifacts]


def _snapshot_world(snapshot: EnvironmentSnapshot) -> dict[str, dict[str, Any]]:
    return {
        item.entity_id: {
            "entity_id": item.entity_id,
            "entity_type": item.entity_type,
            "plane": item.plane,
            "name": item.name,
            "namespace": item.namespace,
            "labels": item.labels,
            "desired_state": item.desired_state,
            "observed_state": item.observed_state,
            "extensions": item.extensions,
        }
        for item in snapshot.entities
    }


def _runtime_context(operation: OperationRun, environment: EnvironmentRecord, snapshot: EnvironmentSnapshot, request_payload: dict[str, Any]) -> RuntimeContext:
    from django.conf import settings

    requested_live = request_payload.get("execution_mode") == "live"
    if requested_live and not settings.KUBEOPS_LIVE_EXECUTION_ENABLED:
        raise PermissionError("live execution is disabled by control-plane policy")
    adapter_mode = "live" if requested_live else "simulation"
    capabilities = set(request_payload.get("capabilities", []))
    if adapter_mode == "simulation" or operation.mode == "dry_run":
        for action in operation.plan.actions:
            capabilities.update(
                action_catalog_for_workspace(_record_workspace_id(environment))
                .get(action.action_type_id)
                .required_capabilities
            )
    world = _snapshot_world(snapshot)
    return RuntimeContext(
        policy_context=PolicyContext(
            environment_class=environment.environment_class,
            environment_fingerprint=request_payload.get("target_fingerprint", environment.fingerprint),
            expected_fingerprint=environment.fingerprint,
            capabilities=frozenset(capabilities),
            mutation_count=len(operation.action_receipts),
        ),
        execution_context=ExecutionContext(
            operation_id=operation.operation_id,
            mode=adapter_mode,
            environment_id=environment.environment_id,
            simulation_world=world,
            metadata={"snapshot_id": snapshot.snapshot_id},
        ),
        world_provider=lambda: world,
        relationships_provider=lambda: snapshot.relationships,
    )


class ActionCatalogView(APIView):
    def get(self, request: Request) -> Response:
        _, workspace_id = requested_scope(request)
        return Response([item.model_dump(mode="json") for item in action_catalog_for_workspace(workspace_id).values()])


class LifecycleProfileListView(APIView):
    def get(self, request: Request) -> Response:
        _, workspace_id = requested_scope(request)
        return Response([item.model_dump(mode="json") for item in lifecycle_registry_for_workspace(workspace_id).values()])


class LifecycleProfileDetailView(APIView):
    def get(self, request: Request, profile_id: str) -> Response:
        try:
            _, workspace_id = requested_scope(request)
            return Response(lifecycle_registry_for_workspace(workspace_id).get(profile_id).model_dump(mode="json"))
        except KeyError:
            return Response({"detail": "lifecycle profile not found"}, status=status.HTTP_404_NOT_FOUND)


class ExecutionPolicyListView(APIView):
    def get(self, request: Request) -> Response:
        return Response([item.model_dump(mode="json") for item in policy_registry().values()])


class SnapshotLifecyclePlanView(APIView):
    def post(self, request: Request, snapshot_id: str) -> Response:
        record = get_object_or_404(EnvironmentSnapshotRecord, snapshot_id=snapshot_id)
        try:
            workspace_id = _record_workspace_id(record.environment)
            profile = lifecycle_registry_for_workspace(workspace_id).get(request.data["lifecycle_profile_id"])
            snapshot = _snapshot(record)
            assessment_record = record.assessments.filter(profile_id=profile.target_operational_profile_id).first()
            assessment = OperationalProfileAssessment.model_validate(assessment_record.payload) if assessment_record else None
            plan = lifecycle_planner_for_workspace(workspace_id).plan(
                profile, snapshot, assessment, mode=request.data.get("mode", "dry_run"),
                policy_id=request.data.get("policy_id")
            )
            return Response(plan.model_dump(mode="json"), status=status.HTTP_201_CREATED)
        except KeyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return _validation_error(exc)


class OperationListCreateView(APIView):
    def get(self, request: Request) -> Response:
        _, workspace_id = requested_scope(request)
        records = OperationRecord.objects.select_related("environment", "snapshot", "incident").filter(
            environment__workspace__workspace_id=workspace_id
        )
        environment_id = request.query_params.get("environment_id")
        if environment_id:
            records = records.filter(environment__environment_id=environment_id)
        return Response([_operation_summary(item) for item in records])

    def post(self, request: Request) -> Response:
        snapshot_record = get_object_or_404(EnvironmentSnapshotRecord, snapshot_id=request.data.get("snapshot_id"))
        environment_record = snapshot_record.environment
        if environment_record.workspace is None:
            return Response({"detail": "environment has no workspace scope"}, status=status.HTTP_409_CONFLICT)
        active_count = OperationRecord.objects.filter(environment__workspace=environment_record.workspace).exclude(
            status__in=["completed", "failed", "cancelled"]
        ).count()
        governance = evaluate_governance(
            workspace=environment_record.workspace, operation="operation.create", active_count=active_count,
            target_id=environment_record.environment_id,
        )
        if governance.outcome != "allow":
            response = Response(governance.model_dump(mode="json"), status=status.HTTP_429_TOO_MANY_REQUESTS)
            if governance.retry_after_seconds is not None:
                response["Retry-After"] = str(governance.retry_after_seconds)
            return response
        try:
            workspace_id = _record_workspace_id(environment_record)
            profile = lifecycle_registry_for_workspace(workspace_id).get(request.data["lifecycle_profile_id"])
            snapshot = _snapshot(snapshot_record)
            assessment_record = snapshot_record.assessments.filter(profile_id=profile.target_operational_profile_id).first()
            assessment = OperationalProfileAssessment.model_validate(assessment_record.payload) if assessment_record else None
            mode = request.data.get("mode", "dry_run")
            plan = lifecycle_planner_for_workspace(workspace_id).plan(
                profile, snapshot, assessment, mode=mode, policy_id=request.data.get("policy_id")
            )
            operation = operation_runtime_for_workspace(workspace_id).create(
                environment_record.environment_id, plan, mode=mode
            )
            operation = operation.model_copy(update={
                "metadata": {**operation.metadata, "governance_decision": governance.model_dump(mode="json")}
            })
            record, artifacts = _persist_operation(operation, environment_record, snapshot_record=snapshot_record)
            mark_governance_usage_terminal(
                workspace=environment_record.workspace, operation="operation.create",
                target_id=environment_record.environment_id,
            )
            payload = record.payload
            payload["artifacts"] = artifacts
            return Response(payload, status=status.HTTP_201_CREATED)
        except KeyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return _validation_error(exc)


class OperationDetailView(APIView):
    def get(self, request: Request, operation_id: str) -> Response:
        record = get_object_or_404(OperationRecord, operation_id=operation_id)
        payload = dict(record.payload)
        payload["artifacts"] = [
            {"artifact_id": item.artifact_id, "artifact_type": item.artifact_type, "content_hash": item.content_hash}
            for item in ArtifactRecord.objects.filter(scope_type="operation", scope_id=operation_id)
        ]
        return Response(payload)


class OperationApprovalView(APIView):
    def post(self, request: Request, operation_id: str) -> Response:
        record = get_object_or_404(OperationRecord, operation_id=operation_id)
        operation = _operation(record)
        approval = ApprovalRecord(
            approval_id=request.data.get("approval_id", f"approval:{operation_id}:{len(operation.approvals)}"),
            operation_id=operation_id,
            action_id=request.data.get("action_id"),
            approver_id=request.data.get("approver_id", "api-operator"),
            decision=request.data.get("decision", "approve"),
            reason=request.data.get("reason", ""),
            granted_at_iso=utc_now_iso(),
            policy_id=operation.plan.policy_id,
        )
        runtime = operation_runtime_for_workspace(_record_workspace_id(record.environment))
        operation = runtime.add_approval(operation, approval)
        updated, artifacts = _persist_operation(operation, record.environment, snapshot_record=record.snapshot, incident_record=record.incident)
        payload = updated.payload
        payload["artifacts"] = artifacts
        return Response(payload, status=status.HTTP_201_CREATED)


class OperationRunView(APIView):
    def post(self, request: Request, operation_id: str) -> Response:
        record = get_object_or_404(OperationRecord, operation_id=operation_id)
        operation = _operation(record)
        snapshot_record = record.snapshot
        if snapshot_record is None:
            return Response({"detail": "operation has no source snapshot"}, status=status.HTTP_409_CONFLICT)
        snapshot = _snapshot(snapshot_record)
        try:
            policy = policy_registry().get(operation.plan.policy_id or "local-development-guarded.v1")
            context = _runtime_context(operation, record.environment, snapshot, dict(request.data))
            finished = operation_runtime_for_workspace(_record_workspace_id(record.environment)).run(
                operation, policy, context
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        updated, artifacts = _persist_operation(finished, record.environment, snapshot_record=snapshot_record, incident_record=record.incident)
        payload = updated.payload
        payload["artifacts"] = artifacts
        return Response(payload, status=status.HTTP_201_CREATED)


class OperationDistributedDispatchView(APIView):
    required_capabilities = {"operation.execute"}

    def post(self, request: Request, operation_id: str) -> Response:
        record = get_object_or_404(OperationRecord, operation_id=operation_id)
        if record.snapshot is None:
            return Response({"detail": "operation has no source snapshot"}, status=status.HTTP_409_CONFLICT)
        operation = _operation(record)
        snapshot = _snapshot(record.snapshot)
        requested_mode = request.data.get("execution_mode", "live")
        if requested_mode not in {"live", "simulation", "dry_run"}:
            return Response({"detail": "execution_mode must be live, simulation, or dry_run"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        try:
            policy = policy_registry().get(operation.plan.policy_id or "local-development-guarded.v1")
            context_payload = dict(request.data)
            context_payload["execution_mode"] = "live" if requested_mode == "live" else "simulation"
            context = _runtime_context(operation, record.environment, snapshot, context_payload)
            runtime = operation_runtime_for_workspace(_record_workspace_id(record.environment))
            authorized = runtime.authorize(operation, policy, context)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        if authorized.status != "authorized":
            updated, artifacts = _persist_operation(
                authorized, record.environment, snapshot_record=record.snapshot, incident_record=record.incident
            )
            payload = dict(updated.payload)
            payload["artifacts"] = artifacts
            return Response(payload, status=status.HTTP_409_CONFLICT)

        if record.environment.workspace is None:
            return Response({"detail": "environment has no workspace scope"}, status=status.HTTP_409_CONFLICT)

        workspace_id = _record_workspace_id(record.environment)
        catalog = action_catalog_for_workspace(workspace_id)
        prepared_actions: list[tuple[ActionInstance, ActionTypeDefinition]] = []
        try:
            for action in authorized.plan.actions:
                definition = catalog.validate_instance(action)
                if requested_mode == "live" and "live" not in definition.supported_modes:
                    return Response(
                        {"detail": f"action {action.action_id} does not support live execution"},
                        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )
                if requested_mode == "simulation" and "simulation" not in definition.supported_modes:
                    return Response(
                        {"detail": f"action {action.action_id} does not support simulation"},
                        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )
                prepared_actions.append((action, definition))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        if not prepared_actions:
            return Response({"detail": "operation has no actions to dispatch"}, status=status.HTTP_409_CONFLICT)

        active_tasks = ExecutionTaskRecord.objects.filter(
            workspace=record.environment.workspace, status__in=["queued", "leased", "running"]
        ).count()
        governance = evaluate_governance(
            workspace=record.environment.workspace, operation="operation.dispatch", active_count=active_tasks,
            target_id=operation_id,
        )
        if governance.outcome != "allow":
            response = Response(governance.model_dump(mode="json"), status=status.HTTP_429_TOO_MANY_REQUESTS)
            if governance.retry_after_seconds is not None:
                response["Retry-After"] = str(governance.retry_after_seconds)
            return response

        now = utc_now_iso()
        tasks: list[ExecutionTask] = []
        try:
            with transaction.atomic():
                for action, definition in prepared_actions:
                    executor_id = (
                        "dry_run" if requested_mode == "dry_run"
                        else "simulation" if requested_mode == "simulation"
                        else definition.executor_id
                    )
                    required_capabilities = (
                        set() if requested_mode in {"dry_run", "simulation"}
                        else set(definition.required_capabilities)
                    )
                    execution_payload = {
                        "action": action.model_dump(mode="json"),
                        "action_definition": definition.model_dump(mode="json"),
                        "mode": requested_mode,
                        "attempt": 1,
                        "depends_on_action_ids": action.depends_on_action_ids,
                        "execution_context": {
                            "command_timeout_seconds": definition.timeout_seconds,
                            "executable_allowlist": request.data.get(
                                "executable_allowlist", ["docker", "kubectl", "systemctl", "service", "kill"]
                            ),
                        },
                    }
                    payload_hash = hashlib.sha256(
                        json.dumps(execution_payload, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest()
                    task = ExecutionTask(
                        task_id=f"task:{operation_id}:{action.action_id}",
                        organization_id=(record.environment.organization.organization_id if record.environment.organization else settings.KUBEOPS_DEFAULT_ORGANIZATION_ID),
                        workspace_id=(record.environment.workspace.workspace_id if record.environment.workspace else settings.KUBEOPS_DEFAULT_WORKSPACE_ID),
                        operation_id=operation_id,
                        action_id=action.action_id,
                        environment_id=record.environment.environment_id,
                        action_type_id=action.action_type_id,
                        executor_id=executor_id,
                        required_capabilities=required_capabilities,
                        target_fingerprint=record.environment.fingerprint,
                        status="queued",
                        priority=int(request.data.get("priority", 0)),
                        attempt=1,
                        max_attempts=definition.max_attempts,
                        idempotency_key=action.idempotency_key,
                        payload=execution_payload,
                        payload_hash=payload_hash,
                        created_at_iso=now,
                        updated_at_iso=now,
                    )
                    tasks.append(task)
                    ExecutionTaskRecord.objects.update_or_create(
                        task_id=task.task_id,
                        defaults={
                            "organization": record.environment.organization,
                            "workspace": record.environment.workspace,
                            "operation": record,
                            "environment": record.environment,
                            "action_id": task.action_id,
                            "action_type_id": task.action_type_id,
                            "executor_id": task.executor_id,
                            "status": task.status,
                            "priority": task.priority,
                            "payload_hash": task.payload_hash,
                            "payload": task.model_dump(mode="json"),
                            "created_at": _dt(task.created_at_iso),
                            "updated_at": _dt(task.updated_at_iso),
                        },
                    )
        except Exception:
            mark_governance_usage_terminal(
                workspace=record.environment.workspace,
                operation="operation.dispatch",
                target_id=operation_id,
            )
            raise
        dispatched = runtime.reconcile_external_receipts(authorized, [])
        dispatched = dispatched.model_copy(
            update={
                "metadata": {
                    **dispatched.metadata,
                    "distributed": True,
                    "distributed_execution_mode": requested_mode,
                    "execution_task_ids": [item.task_id for item in tasks],
                    "dispatch_governance_decision": governance.model_dump(mode="json"),
                }
            }
        )
        runtime.store.save(dispatched)
        updated, artifacts = _persist_operation(
            dispatched, record.environment, snapshot_record=record.snapshot, incident_record=record.incident
        )
        payload = dict(updated.payload)
        payload["execution_tasks"] = [item.model_dump(mode="json") for item in tasks]
        payload["artifacts"] = artifacts
        return Response(payload, status=status.HTTP_201_CREATED)


class OperationDistributedVerifyView(APIView):
    required_capabilities = {"operation.execute"}

    def post(self, request: Request, operation_id: str) -> Response:
        record = get_object_or_404(OperationRecord, operation_id=operation_id)
        operation = _operation(record)
        if operation.status != "verifying":
            return Response(
                {"detail": f"operation cannot be verified from {operation.status}"},
                status=status.HTTP_409_CONFLICT,
            )
        environment = _environment(record.environment)
        profile_ids = request.data.get("profile_ids") or environment.operational_profile_ids
        try:
            workspace_id = _record_workspace_id(record.environment)
            profiles = [profile_registry_for_workspace(workspace_id).get(profile_id) for profile_id in profile_ids]
            history_records = list(record.environment.snapshots.all()[:20])
            history = [_snapshot(item) for item in reversed(history_records)]
            previous = history[-1] if history else None
            result = environment_intelligence_for_workspace(workspace_id).collect(
                environment,
                method_id=request.data.get("method_id"),
                resource_types=request.data.get("resource_types"),
                profiles=profiles,
                history=history,
            )
        except (KeyError, OSError, ValueError, TimeoutError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        snapshot_diff = diff_snapshots(previous, result.snapshot) if previous else None
        snapshot_record, snapshot_artifacts = _persist_snapshot(
            record.environment, result.bundle, result.snapshot, result.topology, result.assessments, snapshot_diff
        )
        world = _snapshot_world(result.snapshot)
        verification_mode = (
            "live"
            if operation.mode != "dry_run"
            and operation.metadata.get("distributed_execution_mode") == "live"
            else "simulation"
        )
        context = RuntimeContext(
            policy_context=PolicyContext(
                environment_class=record.environment.environment_class,
                environment_fingerprint=record.environment.fingerprint,
                expected_fingerprint=record.environment.fingerprint,
                capabilities=frozenset(),
            ),
            execution_context=ExecutionContext(
                operation_id=operation.operation_id,
                mode=verification_mode,
                environment_id=record.environment.environment_id,
                simulation_world=world,
                metadata={"verification_snapshot_id": result.snapshot.snapshot_id},
            ),
            world_provider=lambda: world,
            relationships_provider=lambda: result.snapshot.relationships,
        )
        try:
            runtime = operation_runtime_for_workspace(_record_workspace_id(record.environment))
            finished = runtime.verify_external(operation, context)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        finished = finished.model_copy(
            update={
                "metadata": {
                    **finished.metadata,
                    "verification_snapshot_id": result.snapshot.snapshot_id,
                }
            }
        )
        runtime.store.save(finished)
        updated, artifacts = _persist_operation(
            finished, record.environment, snapshot_record=snapshot_record, incident_record=record.incident
        )
        payload = dict(updated.payload)
        payload["verification_snapshot"] = result.snapshot.model_dump(mode="json")
        payload["snapshot_artifacts"] = snapshot_artifacts
        payload["artifacts"] = artifacts
        return Response(payload, status=status.HTTP_201_CREATED)


class OperationCancelView(APIView):
    def post(self, request: Request, operation_id: str) -> Response:
        record = get_object_or_404(OperationRecord, operation_id=operation_id)
        try:
            operation = operation_runtime_for_workspace(_record_workspace_id(record.environment)).cancel(
                _operation(record), request.data.get("reason", "Cancelled by operator")
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        if record.environment.workspace is not None:
            mark_governance_usage_terminal(
                workspace=record.environment.workspace, operation="operation.dispatch", target_id=operation_id
            )
        updated, artifacts = _persist_operation(
            operation,
            record.environment,
            snapshot_record=record.snapshot,
            incident_record=record.incident,
        )
        payload = updated.payload
        payload["artifacts"] = artifacts
        return Response(payload, status=status.HTTP_201_CREATED)


class OperationPauseView(APIView):
    def post(self, request: Request, operation_id: str) -> Response:
        record = get_object_or_404(OperationRecord, operation_id=operation_id)
        try:
            operation = operation_runtime_for_workspace(_record_workspace_id(record.environment)).pause(
                _operation(record), request.data.get("reason", "Paused by operator")
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        updated, artifacts = _persist_operation(operation, record.environment, snapshot_record=record.snapshot, incident_record=record.incident)
        payload = updated.payload
        payload["artifacts"] = artifacts
        return Response(payload, status=status.HTTP_201_CREATED)


class OperationResumeView(APIView):
    def post(self, request: Request, operation_id: str) -> Response:
        record = get_object_or_404(OperationRecord, operation_id=operation_id)
        if not record.snapshot:
            return Response({"detail": "operation has no source snapshot"}, status=status.HTTP_409_CONFLICT)
        operation = _operation(record)
        snapshot = _snapshot(record.snapshot)
        try:
            policy = policy_registry().get(operation.plan.policy_id or "local-development-guarded.v1")
            context = _runtime_context(operation, record.environment, snapshot, dict(request.data))
            finished = operation_runtime_for_workspace(_record_workspace_id(record.environment)).resume(
                operation_id, policy, context
            )
        except (ValueError, PermissionError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        updated, artifacts = _persist_operation(finished, record.environment, snapshot_record=record.snapshot, incident_record=record.incident)
        payload = updated.payload
        payload["artifacts"] = artifacts
        return Response(payload, status=status.HTTP_201_CREATED)


class OperationRollbackView(APIView):
    def post(self, request: Request, operation_id: str) -> Response:
        record = get_object_or_404(OperationRecord, operation_id=operation_id)
        if not record.snapshot:
            return Response({"detail": "operation has no source snapshot"}, status=status.HTTP_409_CONFLICT)
        operation = _operation(record)
        snapshot = _snapshot(record.snapshot)
        try:
            context = _runtime_context(operation, record.environment, snapshot, dict(request.data))
            finished = operation_runtime_for_workspace(_record_workspace_id(record.environment)).rollback(
                operation, context
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        updated, artifacts = _persist_operation(finished, record.environment, snapshot_record=record.snapshot, incident_record=record.incident)
        payload = updated.payload
        payload["artifacts"] = artifacts
        return Response(payload, status=status.HTTP_201_CREATED)


class OperationCertificateView(APIView):
    def get(self, request: Request, operation_id: str) -> Response:
        record = get_object_or_404(OperationRecord, operation_id=operation_id)
        certificate = record.payload.get("recovery_certificate")
        if certificate is None:
            return Response({"detail": "certificate not available"}, status=status.HTTP_404_NOT_FOUND)
        return Response(certificate)
