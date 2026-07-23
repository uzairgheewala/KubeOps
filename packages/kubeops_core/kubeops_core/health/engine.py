from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from kubeops_core.invariants import InvariantEngine
from kubeops_core.models.discovery import EnvironmentSnapshot
from kubeops_core.models.entity import OperationalEntity
from kubeops_core.models.enums import HealthStatus
from kubeops_core.models.health import (
    CompiledOperationalProfile,
    EntitySelector,
    InvariantTemplate,
    OperationalProfileAssessment,
    OperationalProfileSpec,
)
from kubeops_core.models.invariant import InvariantDefinition
from kubeops_core.models.predicate import (
    FieldEquals,
    FieldExists,
    FieldGte,
    FieldsEqual,
    RelatedCountGte,
)
from kubeops_core.util import get_path, utc_now_iso


def _matches(entity: OperationalEntity, selector: EntitySelector) -> bool:
    if selector.entity_types and not ({entity.entity_type, *entity.entity_type_lineage} & selector.entity_types):
        return False
    if selector.planes and str(entity.plane) not in selector.planes:
        return False
    if selector.names and entity.name not in selector.names:
        return False
    if selector.namespaces and (entity.namespace or "_cluster") not in selector.namespaces:
        return False
    if entity.namespace in selector.exclude_namespaces:
        return False
    if entity.namespace is None and not selector.include_cluster_scoped:
        return False
    return all(entity.labels.get(key) == value for key, value in selector.labels.items())


def _safe_id(value: str) -> str:
    return value.replace("/", "_").replace(":", "_").replace(".", "_")


class ProfileCompiler:
    def compile(
        self,
        profile: OperationalProfileSpec,
        snapshot: EnvironmentSnapshot,
    ) -> CompiledOperationalProfile:
        invariants: list[InvariantDefinition] = []
        required: list[str] = []
        optional: list[str] = []
        unmatched: list[str] = []
        for template in profile.invariant_templates:
            matched = [entity for entity in snapshot.entities if _matches(entity, template.selector)]
            if not matched:
                unmatched.append(template.template_id)
                continue
            for entity in matched:
                invariant = self._compile_template(template, entity)
                invariants.append(invariant)
                (required if template.required else optional).append(invariant.invariant_id)
        return CompiledOperationalProfile(
            profile_id=profile.profile_id,
            version=profile.version,
            environment_id=snapshot.environment_id,
            snapshot_id=snapshot.snapshot_id,
            compiled_at_iso=utc_now_iso(),
            invariants=invariants,
            required_invariant_ids=required,
            optional_invariant_ids=optional,
            unmatched_templates=unmatched,
        )

    def _compile_template(self, template: InvariantTemplate, entity: OperationalEntity) -> InvariantDefinition:
        invariant_id = f"{template.template_id}:{_safe_id(entity.entity_id)}"
        params = template.parameters
        if template.check_type == "entity_observed":
            predicate = FieldExists(entity_id=entity.entity_id, path="observed_state.exists", expected=True)
        elif template.check_type == "field_equals":
            predicate = FieldEquals(entity_id=entity.entity_id, path=str(params["path"]), value=params.get("value"))
        elif template.check_type == "field_gte":
            predicate = FieldGte(entity_id=entity.entity_id, path=str(params["path"]), value=float(params.get("value", 0)))
        elif template.check_type == "fields_equal":
            predicate = FieldsEqual(
                left_entity_id=entity.entity_id,
                left_path=str(params["left_path"]),
                right_entity_id=entity.entity_id,
                right_path=str(params["right_path"]),
            )
        elif template.check_type == "node_ready":
            predicate = FieldEquals(entity_id=entity.entity_id, path="observed_state.ready", value=True)
        elif template.check_type == "pod_ready":
            predicate = FieldEquals(entity_id=entity.entity_id, path="observed_state.ready", value=True)
        elif template.check_type == "workload_available":
            kind = str(get_path(entity.extensions, "kubernetes.kind", ""))
            if kind == "DaemonSet":
                desired = int(entity.observed_state.get("desired_number_scheduled", 0) or 0)
                path = "observed_state.number_ready"
            else:
                desired = int(entity.desired_state.get("replicas", 1) or 0)
                path = "observed_state.ready_replicas"
            predicate = FieldGte(entity_id=entity.entity_id, path=path, value=desired)
        elif template.check_type == "controller_progress":
            predicate = FieldsEqual(
                left_entity_id=entity.entity_id,
                left_path="observed_state.generation",
                right_entity_id=entity.entity_id,
                right_path="observed_state.observed_generation",
            )
        elif template.check_type == "service_has_ready_endpoints":
            predicate = RelatedCountGte(
                source_entity_id=entity.entity_id,
                relationship_types={"selects"},
                direction="outgoing",
                target_path="observed_state.ready",
                target_equals=True,
                minimum=int(params.get("minimum", 1)),
            )
        elif template.check_type == "pvc_bound":
            predicate = FieldEquals(entity_id=entity.entity_id, path="observed_state.bound", value=True)
        else:  # pragma: no cover - model validation prevents this
            raise ValueError(f"unsupported check type {template.check_type}")
        return InvariantDefinition(
            invariant_id=invariant_id,
            title=f"{template.title}: {entity.namespace + '/' if entity.namespace else ''}{entity.name}",
            family=template.family,
            subject_id=entity.entity_id,
            predicate=predicate,
            severity=template.severity,
            temporal=template.temporal,
            description=template.description,
            affected_objectives=template.affected_objectives,
        )


class HealthAssessmentEngine:
    def __init__(self) -> None:
        self._compiler = ProfileCompiler()
        self._invariants = InvariantEngine()

    def assess(
        self,
        profile: OperationalProfileSpec,
        snapshot: EnvironmentSnapshot,
        history: list[EnvironmentSnapshot] | None = None,
    ) -> OperationalProfileAssessment:
        compiled = self._compiler.compile(profile, snapshot)
        world = {entity.entity_id: entity.model_dump(mode="json") for entity in snapshot.entities}
        current_time = self._seconds(snapshot.completed_at_iso)
        observed_history = [
            (self._seconds(item.completed_at_iso), {entity.entity_id: entity.model_dump(mode="json") for entity in item.entities})
            for item in sorted(history or [snapshot], key=lambda item: item.completed_at_iso)
            if item.environment_id == snapshot.environment_id and item.completed_at_iso <= snapshot.completed_at_iso
        ]
        if not observed_history:
            observed_history = [(current_time, world)]
        evaluations = self._invariants.evaluate_all(
            compiled.invariants,
            world,
            current_time,
            observed_history=observed_history,
            relationships=snapshot.relationships,
        )
        by_id = {item.invariant_id: item for item in evaluations}
        required_evals = [by_id[item] for item in compiled.required_invariant_ids if item in by_id]
        optional_evals = [by_id[item] for item in compiled.optional_invariant_ids if item in by_id]
        status = self._aggregate(required_evals, optional_evals, compiled.unmatched_templates)
        violated = [item.invariant_id for item in evaluations if item.status == HealthStatus.UNHEALTHY]
        unknown = [item.invariant_id for item in evaluations if item.status == HealthStatus.UNKNOWN]
        pending = [item.invariant_id for item in evaluations if item.status == HealthStatus.PENDING]
        counts: dict[str, int] = {}
        for evaluation in evaluations:
            counts[str(evaluation.status)] = counts.get(str(evaluation.status), 0) + 1
        objective_impact: dict[str, list[str]] = {}
        definitions = {item.invariant_id: item for item in compiled.invariants}
        for invariant_id in [*violated, *unknown, *pending]:
            for objective in definitions[invariant_id].affected_objectives:
                objective_impact.setdefault(objective, []).append(invariant_id)
        return OperationalProfileAssessment(
            assessment_id=f"profile-assessment:{uuid4()}",
            profile_id=profile.profile_id,
            profile_version=profile.version,
            environment_id=snapshot.environment_id,
            snapshot_id=snapshot.snapshot_id,
            evaluated_at_iso=utc_now_iso(),
            status=status,
            evaluations=evaluations,
            required_invariant_ids=compiled.required_invariant_ids,
            optional_invariant_ids=compiled.optional_invariant_ids,
            violated_invariant_ids=violated,
            unknown_invariant_ids=unknown,
            pending_invariant_ids=pending,
            counts=counts,
            objective_impact=objective_impact,
            metadata={
                "unmatched_templates": compiled.unmatched_templates,
                "compiled_invariant_count": len(compiled.invariants),
                "snapshot_status": snapshot.status,
                "permission_gap_count": len(snapshot.permission_gaps),
            },
        )

    @staticmethod
    def _seconds(value: str) -> int:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())

    @staticmethod
    def _aggregate(required: list[Any], optional: list[Any], unmatched_templates: list[str]) -> HealthStatus:
        if any(item.status == HealthStatus.UNHEALTHY for item in required):
            return HealthStatus.UNHEALTHY
        if any(item.status == HealthStatus.UNKNOWN for item in required) or (not required and unmatched_templates):
            return HealthStatus.UNKNOWN
        if any(item.status == HealthStatus.PENDING for item in required):
            return HealthStatus.PENDING
        if any(item.status in {HealthStatus.UNHEALTHY, HealthStatus.UNKNOWN, HealthStatus.PENDING} for item in optional):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY
