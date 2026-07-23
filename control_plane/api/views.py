from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from kubeops_core import __version__ as core_version
from kubeops_core.artifacts import build_run_artifacts
from kubeops_core.models import (
    ActionInstance,
    ActionTypeDefinition,
    DiagnosisCertificate,
    EvidenceIntent,
    ExecutionPolicy,
    Hypothesis,
    InvariantDefinition,
    Observation,
    ObservationProfile,
    OperationalEntity,
    OperationalObjective,
    OperationalProfile,
    PolicyDecision,
    ProbeIntent,
    RecoveryCertificate,
    RecoveryPlan,
    Relationship,
    RunArtifact,
    ScenarioComposition,
    ScenarioFamily,
    ScenarioInstance,
    SimulationRun,
    Symptom,
    VerificationCondition,
    VerificationResult,
)
from kubeops_core.scenarios import ScenarioCompileError, ScenarioComposer

from .models import ArtifactRecord, OperationEventRecord, ScenarioRunRecord
from .services import artifact_store, registry_catalog, scenario_compiler, scenario_registry, simulation_engine


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
            completed_at=parse_datetime(run.completed_at_iso) if run.completed_at_iso else None,
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
        {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "content_hash": artifact.payload_hash,
        }
        for artifact in artifacts
    ]


class SystemStatusView(APIView):
    def get(self, request: Request) -> Response:
        registry = scenario_registry()
        return Response(
            {
                "service": "kubeops-control-plane",
                "release": "0.1.0",
                "core_version": core_version,
                "mode": "simulation",
                "status": "ok",
                "family_count": len(registry),
                "capabilities": [
                    "canonical_ir",
                    "family_inheritance",
                    "scenario_compilation",
                    "scenario_composition",
                    "deterministic_simulation",
                    "temporal_invariants",
                    "partial_observation",
                    "artifact_persistence",
                    "forward_compatible_diagnosis_ir",
                    "forward_compatible_recovery_ir",
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
            OperationalEntity,
            Relationship,
            OperationalObjective,
            OperationalProfile,
            InvariantDefinition,
            Observation,
            ObservationProfile,
            EvidenceIntent,
            Symptom,
            Hypothesis,
            ProbeIntent,
            ScenarioFamily,
            ScenarioInstance,
            ScenarioComposition,
            ActionTypeDefinition,
            ActionInstance,
            ExecutionPolicy,
            PolicyDecision,
            RecoveryPlan,
            VerificationCondition,
            VerificationResult,
            DiagnosisCertificate,
            RecoveryCertificate,
            SimulationRun,
            RunArtifact,
        ]
    }

    def get(self, request: Request, schema_name: str) -> Response:
        model = self.schema_types.get(schema_name)
        if model is None:
            return Response({"detail": "schema not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(model.model_json_schema())


class ScenarioFamilyListView(APIView):
    def get(self, request: Request) -> Response:
        registry = scenario_registry()
        payload = []
        compiler = scenario_compiler()
        for family in registry.values():
            effective = compiler.effective_family(family.family_id)
            item = effective.model_dump(mode="json")
            item["content_hash"] = effective.content_hash
            item["lineage"] = [node.family_id for node in registry.lineage(family.family_id)]
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
            errors = getattr(exc, "errors", [str(exc)])
            return Response({"errors": errors}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(scenario.model_dump(mode="json"), status=status.HTTP_201_CREATED)


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
            errors = getattr(exc, "errors", [str(exc)])
            return Response({"errors": errors}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        run = simulation_engine().run(scenario, seed=int(payload.get("seed", 0)))
        artifact_summaries = _persist_run(scenario, run)
        response = run.model_dump(mode="json")
        response["scenario"] = scenario.model_dump(mode="json")
        response["artifacts"] = artifact_summaries
        return Response(response, status=status.HTTP_201_CREATED)


class CompositionCompileView(APIView):
    def post(self, request: Request) -> Response:
        try:
            spec = ScenarioComposition.model_validate(request.data)
            scenario = ScenarioComposer(scenario_compiler()).compose(spec)
        except (ValueError, ScenarioCompileError) as exc:
            errors = getattr(exc, "errors", None)
            if callable(errors):
                errors = [item.get("msg", str(item)) for item in errors()]
            if not errors:
                errors = getattr(exc, "errors", [str(exc)])
            return Response({"errors": errors}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(scenario.model_dump(mode="json"), status=status.HTTP_201_CREATED)


class CompositionRunView(APIView):
    def post(self, request: Request) -> Response:
        try:
            spec = ScenarioComposition.model_validate(request.data)
            scenario = ScenarioComposer(scenario_compiler()).compose(spec)
        except (ValueError, ScenarioCompileError) as exc:
            errors = getattr(exc, "errors", None)
            if callable(errors):
                errors = [item.get("msg", str(item)) for item in errors()]
            if not errors:
                errors = getattr(exc, "errors", [str(exc)])
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
        if run_id:
            queryset = queryset.filter(run__run_id=run_id)
        return Response(
            [
                {
                    "artifact_id": artifact.artifact_id,
                    "run_id": artifact.run.run_id,
                    "artifact_type": artifact.artifact_type,
                    "content_hash": artifact.content_hash,
                    "media_type": artifact.media_type,
                    "derived_from": artifact.derived_from,
                    "created_at": artifact.created_at,
                }
                for artifact in queryset[:500]
            ]
        )


class ArtifactDetailView(APIView):
    def get(self, request: Request, artifact_id: str) -> Response:
        record = get_object_or_404(
            ArtifactRecord.objects.select_related("run"), artifact_id=artifact_id
        )
        artifact = artifact_store().get(record.run.run_id, record.artifact_id)
        payload = artifact.model_dump(mode="json")
        payload["content_hash"] = payload.pop("payload_hash")
        return Response(payload)


class ScenarioRunListView(APIView):
    def get(self, request: Request) -> Response:
        records = ScenarioRunRecord.objects.all()[:100]
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
                for record in records
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
