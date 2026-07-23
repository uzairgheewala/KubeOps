from __future__ import annotations

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
from kubeops_core.artifacts import build_incident_artifacts, build_run_artifacts, build_snapshot_artifacts
from kubeops_core.discovery import diff_snapshots, export_discovery_fixture
from kubeops_core.health import HealthAssessmentEngine
from kubeops_core.models import (
    AccessMethodDefinition,
    AccessValidationResult,
    ActionInstance,
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
)
from kubeops_core.scenarios import ScenarioCompileError, ScenarioComposer
from kubeops_core.topology import TopologyCompiler

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
    OperationalProfileRecord,
    ProfileAssessmentRecord,
    ProbeRunRecord,
    ScenarioRunRecord,
    SnapshotEntityRecord,
    SnapshotRelationshipRecord,
)
from .services import (
    artifact_store,
    diagnostic_catalog,
    environment_intelligence,
    investigation_service,
    profile_registry,
    registry_catalog,
    scenario_compiler,
    scenario_diagnosis_evaluator,
    scenario_registry,
    simulation_engine,
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


def _environment(record: EnvironmentRecord) -> EnvironmentDefinition:
    return EnvironmentDefinition.model_validate(record.payload)


def _snapshot(record: EnvironmentSnapshotRecord) -> EnvironmentSnapshot:
    return EnvironmentSnapshot.model_validate(record.payload)


def _persist_run(scenario: ScenarioInstance, run: SimulationRun) -> list[dict[str, str]]:
    artifacts = build_run_artifacts(scenario, run)
    paths = {artifact.artifact_id: artifact_store().put(artifact) for artifact in artifacts}
    with transaction.atomic():
        run_record = ScenarioRunRecord.objects.create(
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
    defaults = {
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


class SystemStatusView(APIView):
    def get(self, request: Request) -> Response:
        return Response(
            {
                "service": "kubeops-control-plane",
                "release": "0.3.0",
                "core_version": core_version,
                "mode": "read_only_diagnosis",
                "status": "ok",
                "family_count": len(scenario_registry()),
                "profile_count": len(profile_registry()),
                "environment_count": EnvironmentRecord.objects.filter(active=True).count(),
                "incident_count": IncidentRecord.objects.count(),
                "diagnostic_intent_count": len(diagnostic_catalog().intents()),
                "diagnostic_collector_count": len(diagnostic_catalog().collectors()),
                "causal_template_count": len(diagnostic_catalog().templates()),
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
                ],
            }
        )


class RegistryView(APIView):
    def get(self, request: Request) -> Response:
        payload = registry_catalog().snapshot().model_dump(mode="json")
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
            RunArtifact, OperationalArtifact, AccessMethodDefinition, EnvironmentDefinition,
            AccessValidationResult, DiscoveryBundle, EnvironmentSnapshot, SnapshotDiff,
            TopologyGraph, OperationalProfileSpec, CompiledOperationalProfile,
            OperationalProfileAssessment,
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
        for profile in profile_registry().values():
            item = profile.model_dump(mode="json")
            item["content_hash"] = profile.content_hash
            payload.append(item)
        return Response(payload)


class OperationalProfileDetailView(APIView):
    def get(self, request: Request, profile_id: str) -> Response:
        try:
            profile = profile_registry().get(profile_id)
        except KeyError:
            return Response({"detail": "operational profile not found"}, status=status.HTTP_404_NOT_FOUND)
        payload = profile.model_dump(mode="json")
        payload["content_hash"] = profile.content_hash
        return Response(payload)


class EnvironmentListView(APIView):
    def get(self, request: Request) -> Response:
        records = EnvironmentRecord.objects.prefetch_related("snapshots__assessments", "access_validations").filter(active=True)
        return Response([_environment_summary(record) for record in records])

    def post(self, request: Request) -> Response:
        try:
            environment = EnvironmentDefinition.model_validate(request.data)
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
            result = environment_intelligence().validate(_environment(record), request.data.get("method_id"))
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
            profiles = [profile_registry().get(profile_id) for profile_id in profile_ids]
        except KeyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        history_records = list(record.snapshots.all()[:20])
        history = [_snapshot(item) for item in reversed(history_records)]
        previous = history[-1] if history else None
        try:
            result = environment_intelligence().collect(
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
            profile = profile_registry().get(profile_id)
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
        catalog = diagnostic_catalog()
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
        queryset = IncidentRecord.objects.select_related("environment", "snapshot").all()
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
            profile = profile_registry().get(profile_id)
        except KeyError:
            return Response({"detail": "operational profile not found"}, status=status.HTTP_404_NOT_FOUND)
        snapshot = _snapshot(snapshot_record)
        topology = TopologyCompiler().compile_snapshot(snapshot)
        history_records = list(
            snapshot_record.environment.snapshots.filter(captured_at__lte=snapshot_record.captured_at).order_by("captured_at")
        )
        incident = investigation_service().open(
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
            profile = profile_registry().get(incident.profile_id)
        except KeyError:
            return Response({"detail": "operational profile not found"}, status=status.HTTP_404_NOT_FOUND)
        snapshot = _snapshot(record.snapshot)
        topology = TopologyCompiler().compile_snapshot(snapshot)
        history_records = list(
            record.environment.snapshots.filter(captured_at__lte=record.snapshot.captured_at).order_by("captured_at")
        )
        try:
            refined = investigation_service().run_probe(
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
        catalog = diagnostic_catalog()
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
        result = scenario_diagnosis_evaluator().evaluate(scenario, run, expectation)
        response = result.model_dump(mode="json")
        response["run"] = run.model_dump(mode="json")
        response["scenario"] = scenario.model_dump(mode="json")
        response["artifacts"] = _persist_run(scenario, run)
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
        response["artifacts"] = _persist_run(scenario, run)
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
        response["artifacts"] = _persist_run(scenario, run)
        return Response(response, status=status.HTTP_201_CREATED)


class ArtifactListView(APIView):
    def get(self, request: Request) -> Response:
        queryset = ArtifactRecord.objects.select_related("run").all()
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
        record = get_object_or_404(ArtifactRecord.objects.select_related("run"), artifact_id=artifact_id)
        scope_id = record.scope_id or (record.run.run_id if record.run else "")
        artifact = artifact_store().get(scope_id, record.artifact_id)
        payload = artifact.model_dump(mode="json")
        payload["content_hash"] = payload.pop("payload_hash")
        return Response(payload)


class ScenarioRunListView(APIView):
    def get(self, request: Request) -> Response:
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
                for record in ScenarioRunRecord.objects.all()[:100]
            ]
        )


class ScenarioRunDetailView(APIView):
    def get(self, request: Request, run_id: str) -> Response:
        record = get_object_or_404(ScenarioRunRecord, run_id=run_id)
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
