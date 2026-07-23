from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from kubeops_core.models.diagnosis import (
    CollectorDefinition,
    CollectorPlanStep,
    CollectorRunResult,
    EvidenceCollectionPlan,
    EvidenceFact,
    EvidenceIntent,
)
from kubeops_core.models.discovery import EnvironmentSnapshot
from kubeops_core.models.entity import OperationalEntity
from kubeops_core.models.health import OperationalProfileAssessment
from kubeops_core.models.topology import TopologyGraph
from kubeops_core.util import get_path, utc_now_iso

from .catalog import DiagnosticCatalog


_COST = {"negligible": 0.25, "low": 1.0, "medium": 3.0, "high": 8.0}
_AUTHORITY = {"heuristic": 0, "low": 1, "medium": 2, "high": 3, "authoritative": 4}


@dataclass(frozen=True)
class EvidenceContext:
    snapshot: EnvironmentSnapshot
    topology: TopologyGraph
    assessments: tuple[OperationalProfileAssessment, ...] = ()
    mode: str = "fixture"
    available_capabilities: frozenset[str] = frozenset({"snapshot", "topology"})

    @property
    def entities(self) -> dict[str, OperationalEntity]:
        return {item.entity_id: item for item in self.snapshot.entities}


class EvidencePlanner:
    def __init__(self, catalog: DiagnosticCatalog) -> None:
        self._catalog = catalog

    def plan(
        self,
        intents: list[EvidenceIntent],
        context: EvidenceContext,
        *,
        incident_id: str | None = None,
        existing_fact_types: set[str] | None = None,
    ) -> EvidenceCollectionPlan:
        existing = existing_fact_types or set()
        steps: list[CollectorPlanStep] = []
        unresolved: list[str] = []
        selected: set[tuple[str, str, tuple[str, ...]]] = set()
        total_cost = 0.0

        for intent in intents:
            required = {
                fact_type
                for fact_type in intent.required_fact_types
                if not any(_fact_type_matches(fact_type, item) for item in existing)
            }
            if not required and intent.required_fact_types:
                continue
            candidates = self._candidates(intent, context)
            covered: set[str] = set()
            for definition, score in candidates:
                expected = sorted(
                    fact_type
                    for fact_type in definition.fact_types
                    if not required or any(_fact_type_matches(req, fact_type) for req in required)
                )
                if required and not expected:
                    continue
                identity = (definition.collector_id, intent.intent_id, tuple(sorted(intent.subject_ids)))
                if identity in selected:
                    continue
                selected.add(identity)
                step = CollectorPlanStep(
                    step_id=f"step-{uuid4().hex[:12]}",
                    collector_id=definition.collector_id,
                    intent_id=intent.intent_id,
                    subject_ids=intent.subject_ids,
                    questions_answered=sorted(set(definition.questions_answered) & set(intent.questions_answered)),
                    expected_fact_types=expected or definition.fact_types,
                    rationale=(
                        f"Answers {len(set(definition.questions_answered) & set(intent.questions_answered))} "
                        f"requested questions at {definition.cost_class} cost using {definition.authority} evidence."
                    ),
                    score=score,
                )
                steps.append(step)
                total_cost += _COST[definition.cost_class]
                covered.update(expected)
                if intent.stopping_condition == "first_authoritative_answer" and definition.authority == "authoritative":
                    break
                if required and all(any(_fact_type_matches(req, item) for item in covered) for req in required):
                    break
            if required and not all(any(_fact_type_matches(req, item) for item in covered) for req in required):
                unresolved.append(intent.intent_id)

        return EvidenceCollectionPlan(
            plan_id=f"evidence-plan-{uuid4().hex[:12]}",
            incident_id=incident_id,
            environment_id=context.snapshot.environment_id,
            snapshot_id=context.snapshot.snapshot_id,
            created_at_iso=utc_now_iso(),
            intents=intents,
            steps=sorted(steps, key=lambda item: (-item.score, item.step_id)),
            unresolved_intent_ids=unresolved,
            estimated_cost_score=round(total_cost, 3),
            metadata={"mode": context.mode},
        )

    def _candidates(
        self,
        intent: EvidenceIntent,
        context: EvidenceContext,
    ) -> list[tuple[CollectorDefinition, float]]:
        candidates: list[tuple[CollectorDefinition, float]] = []
        for definition in self._catalog.collectors():
            if context.mode not in definition.supported_modes:
                continue
            if not definition.required_capabilities.issubset(context.available_capabilities):
                continue
            if not definition.required_inputs.issubset(context.available_capabilities):
                continue
            question_overlap = len(set(definition.questions_answered) & set(intent.questions_answered))
            fact_overlap = len(
                [
                    required
                    for required in intent.required_fact_types
                    if any(_fact_type_matches(required, provided) for provided in definition.fact_types)
                ]
            )
            preferred = definition.collector_id in intent.preferred_collector_ids
            if question_overlap == 0 and fact_overlap == 0 and not preferred:
                continue
            authority_delta = _AUTHORITY[definition.authority] - _AUTHORITY[intent.required_authority]
            score = question_overlap * 3.0 + fact_overlap * 4.0 + (3.0 if preferred else 0.0)
            score += max(authority_delta, -2) * 0.5
            score -= _COST[definition.cost_class] * 0.25
            candidates.append((definition, score))
        return sorted(candidates, key=lambda item: (-item[1], item[0].collector_id))


class EvidenceExecutor:
    def __init__(self, catalog: DiagnosticCatalog) -> None:
        self._catalog = catalog
        self._handlers: dict[str, Callable[[CollectorPlanStep, EvidenceContext], list[EvidenceFact]]] = {
            "entity_state": self._entity_state,
            "conditions": self._conditions,
            "topology_neighborhood": self._topology_neighborhood,
            "endpoint_state": self._endpoint_state,
            "authentication_state": self._authentication_state,
            "authorization_state": self._authorization_state,
            "controller_progress": self._controller_progress,
            "placement_state": self._placement_state,
            "capacity_state": self._capacity_state,
            "reference_state": self._reference_state,
            "discovery_issues": self._discovery_issues,
            "permission_gaps": self._permission_gaps,
            "observability_quality": self._observability_quality,
        }

    def execute(
        self,
        plan: EvidenceCollectionPlan,
        context: EvidenceContext,
    ) -> list[CollectorRunResult]:
        results: list[CollectorRunResult] = []
        for step in plan.steps:
            started = utc_now_iso()
            definition = self._catalog.collector(step.collector_id)
            handler = self._handlers.get(definition.handler_id)
            if handler is None:
                results.append(
                    CollectorRunResult(
                        run_id=f"collector-run-{uuid4().hex[:12]}",
                        step_id=step.step_id,
                        collector_id=definition.collector_id,
                        intent_id=step.intent_id,
                        status="failed",
                        started_at_iso=started,
                        completed_at_iso=utc_now_iso(),
                        errors=[f"no handler registered for {definition.handler_id}"],
                    )
                )
                continue
            try:
                evidence = handler(step, context)
                status = "completed" if evidence else "partial"
                errors = [] if evidence else ["collector produced no facts for the selected subjects"]
            except Exception as exc:  # collector failure is data, not an investigation crash
                evidence = []
                status = "failed"
                errors = [f"{type(exc).__name__}: {exc}"]
            results.append(
                CollectorRunResult(
                    run_id=f"collector-run-{uuid4().hex[:12]}",
                    step_id=step.step_id,
                    collector_id=definition.collector_id,
                    intent_id=step.intent_id,
                    status=status,
                    started_at_iso=started,
                    completed_at_iso=utc_now_iso(),
                    evidence=evidence,
                    errors=errors,
                )
            )
        return results

    def _subjects(self, step: CollectorPlanStep, context: EvidenceContext) -> list[str]:
        if step.subject_ids:
            return list(dict.fromkeys(step.subject_ids))
        return sorted(context.entities)

    def _fact(
        self,
        step: CollectorPlanStep,
        context: EvidenceContext,
        fact_type: str,
        statement: str,
        *,
        subjects: list[str],
        value: Any = None,
        attributes: dict[str, Any] | None = None,
        authority: str = "authoritative",
    ) -> EvidenceFact:
        token = f"{context.snapshot.snapshot_id}:{step.collector_id}:{step.intent_id}:{fact_type}:{subjects}:{value}:{attributes}"
        import hashlib

        evidence_id = f"ev-{hashlib.sha256(token.encode()).hexdigest()[:20]}"
        return EvidenceFact(
            evidence_id=evidence_id,
            fact_type=fact_type,
            statement=statement,
            value=value,
            subject_ids=subjects,
            intent_id=step.intent_id,
            collector_id=step.collector_id,
            observed_at_iso=context.snapshot.completed_at_iso,
            authority=authority,  # type: ignore[arg-type]
            freshness_seconds=0,
            attributes=attributes or {},
        )

    def _entity_state(self, step: CollectorPlanStep, context: EvidenceContext) -> list[EvidenceFact]:
        facts: list[EvidenceFact] = []
        entities = context.entities
        for subject_id in self._subjects(step, context):
            entity = entities.get(subject_id)
            if entity is None:
                facts.extend(
                    [
                        self._fact(step, context, "entity.exists", f"{subject_id} is not present in the snapshot.", subjects=[subject_id], value=False),
                        self._fact(step, context, "entity.exists.false", f"{subject_id} is absent.", subjects=[subject_id], value=False),
                        self._fact(step, context, "entity.absent", f"Required entity {subject_id} is absent.", subjects=[subject_id], value=True),
                    ]
                )
                continue
            facts.append(self._fact(step, context, "entity.exists", f"{subject_id} exists.", subjects=[subject_id], value=True))
            facts.append(self._fact(step, context, "entity.exists.true", f"{subject_id} exists.", subjects=[subject_id], value=True))
            facts.append(
                self._fact(
                    step,
                    context,
                    "entity.state",
                    f"Current normalized state captured for {subject_id}.",
                    subjects=[subject_id],
                    value={"desired": entity.desired_state, "observed": entity.observed_state},
                    attributes={"entity_type": entity.entity_type, "plane": str(entity.plane)},
                )
            )
            for field in ["ready", "serviceable", "reachable", "authenticated", "authorized", "bound"]:
                value = entity.observed_state.get(field)
                if isinstance(value, bool):
                    facts.append(
                        self._fact(
                            step,
                            context,
                            f"entity.{field}.{str(value).lower()}",
                            f"{subject_id} reports {field}={value}.",
                            subjects=[subject_id],
                            value=value,
                        )
                    )
        return facts

    def _conditions(self, step: CollectorPlanStep, context: EvidenceContext) -> list[EvidenceFact]:
        facts: list[EvidenceFact] = []
        for subject_id in self._subjects(step, context):
            entity = context.entities.get(subject_id)
            if entity is None:
                continue
            conditions = entity.observed_state.get("conditions", {})
            if not isinstance(conditions, dict):
                continue
            for condition_type, condition in sorted(conditions.items()):
                condition = condition if isinstance(condition, dict) else {"status": condition}
                status = condition.get("status")
                reason = condition.get("reason")
                facts.append(
                    self._fact(
                        step,
                        context,
                        "kubernetes.condition",
                        f"{subject_id} condition {condition_type}={status}"
                        + (f" ({reason})" if reason else ""),
                        subjects=[subject_id],
                        value=condition,
                        attributes={"condition_type": condition_type, "status": status, "reason": reason},
                    )
                )
        return facts

    def _topology_neighborhood(self, step: CollectorPlanStep, context: EvidenceContext) -> list[EvidenceFact]:
        facts: list[EvidenceFact] = []
        subjects = set(self._subjects(step, context))
        for subject_id in sorted(subjects):
            incoming = [item for item in context.topology.relationships if item.target_id == subject_id]
            outgoing = [item for item in context.topology.relationships if item.source_id == subject_id]
            neighbors = sorted({item.source_id for item in incoming} | {item.target_id for item in outgoing})
            facts.append(
                self._fact(
                    step,
                    context,
                    "topology.neighborhood",
                    f"{subject_id} has {len(incoming)} incoming and {len(outgoing)} outgoing operational relationships.",
                    subjects=[subject_id, *neighbors],
                    value={"incoming": [item.model_dump(mode="json") for item in incoming], "outgoing": [item.model_dump(mode="json") for item in outgoing]},
                )
            )
            for relationship in [*incoming, *outgoing]:
                facts.append(
                    self._fact(
                        step,
                        context,
                        "dependency.edge",
                        f"{relationship.source_id} --{relationship.relationship_type}--> {relationship.target_id}.",
                        subjects=[relationship.source_id, relationship.target_id],
                        value=relationship.model_dump(mode="json"),
                        attributes={"relationship_type": relationship.relationship_type},
                    )
                )
        return facts

    def _endpoint_state(self, step: CollectorPlanStep, context: EvidenceContext) -> list[EvidenceFact]:
        facts: list[EvidenceFact] = []
        for subject_id in self._subjects(step, context):
            entity = context.entities.get(subject_id)
            if entity is None:
                facts.append(self._fact(step, context, "endpoint.reachable.false", f"Endpoint entity {subject_id} is absent.", subjects=[subject_id], value=False, attributes={"layer": "endpoint_presence"}))
                facts.append(self._fact(step, context, "endpoint.layer", f"Endpoint presence failed for {subject_id}.", subjects=[subject_id], value="endpoint_presence"))
                continue
            observed = entity.observed_state
            reachable = observed.get("reachable")
            failed_layer = observed.get("failed_layer") or observed.get("failure_layer")
            if reachable is None:
                ready = observed.get("ready")
                if isinstance(ready, bool) and entity.entity_type in {"kubernetes.pod", "kubernetes.service"}:
                    reachable = ready
                elif entity.entity_type == "kubernetes.service":
                    selected = [item for item in context.topology.relationships if item.source_id == subject_id and item.relationship_type == "selects"]
                    if selected:
                        reachable = any(context.entities.get(item.target_id) and context.entities[item.target_id].observed_state.get("ready") is True for item in selected)
                        failed_layer = "endpoint_presence" if not reachable else None
            if isinstance(reachable, bool):
                facts.append(self._fact(step, context, "endpoint.reachable", f"Endpoint reachability for {subject_id} is {reachable}.", subjects=[subject_id], value=reachable))
                facts.append(self._fact(step, context, f"endpoint.reachable.{str(reachable).lower()}", f"Endpoint {subject_id} is {'reachable' if reachable else 'unreachable'}.", subjects=[subject_id], value=reachable))
            if failed_layer:
                facts.append(self._fact(step, context, "endpoint.layer", f"Endpoint failure for {subject_id} is localized to {failed_layer}.", subjects=[subject_id], value=failed_layer, attributes={"layer": failed_layer}))
        return facts

    def _authentication_state(self, step: CollectorPlanStep, context: EvidenceContext) -> list[EvidenceFact]:
        facts: list[EvidenceFact] = []
        for subject_id in self._subjects(step, context):
            entity = context.entities.get(subject_id)
            if entity is None:
                continue
            state = entity.observed_state
            auth = state.get("authentication") if isinstance(state.get("authentication"), dict) else {}
            values = {
                "authenticated": state.get("authenticated", auth.get("succeeded")),
                "credential_present": state.get("credential_present", auth.get("credential_present")),
                "credential_fresh": state.get("credential_fresh", auth.get("credential_fresh")),
                "credential_propagated": state.get("credential_propagated", auth.get("credential_propagated")),
                "status_code": state.get("status_code", auth.get("status_code")),
            }
            if any(value is not None for value in values.values()):
                failed = values["authenticated"] is False or values["status_code"] == 401 or any(values[key] is False for key in ["credential_present", "credential_fresh", "credential_propagated"])
                facts.append(self._fact(step, context, "authentication.state", f"Authentication chain state captured for {subject_id}.", subjects=[subject_id], value=values))
                facts.append(self._fact(step, context, "authentication.state.failed" if failed else "authentication.state.succeeded", f"Authentication for {subject_id} {'failed' if failed else 'succeeded'}.", subjects=[subject_id], value=not failed))
                if failed:
                    facts.append(self._fact(step, context, "authentication.failure", f"Authentication evidence indicates failure for {subject_id}.", subjects=[subject_id], value=values))
        return facts

    def _authorization_state(self, step: CollectorPlanStep, context: EvidenceContext) -> list[EvidenceFact]:
        facts: list[EvidenceFact] = []
        for subject_id in self._subjects(step, context):
            entity = context.entities.get(subject_id)
            if entity is None:
                continue
            state = entity.observed_state
            authorized = state.get("authorized")
            status_code = state.get("status_code")
            if authorized is None and status_code in {403}:
                authorized = False
            if isinstance(authorized, bool):
                facts.append(self._fact(step, context, "authorization.state", f"Authorization decision for {subject_id} is {authorized}.", subjects=[subject_id], value=authorized))
                facts.append(self._fact(step, context, "authorization.allowed" if authorized else "authorization.denied", f"Authorization for {subject_id} was {'allowed' if authorized else 'denied'}.", subjects=[subject_id], value=authorized))
        return facts

    def _controller_progress(self, step: CollectorPlanStep, context: EvidenceContext) -> list[EvidenceFact]:
        facts: list[EvidenceFact] = []
        for subject_id in self._subjects(step, context):
            entity = context.entities.get(subject_id)
            if entity is None:
                continue
            generation = entity.observed_state.get("generation")
            observed_generation = entity.observed_state.get("observed_generation")
            progress = entity.observed_state.get("progressing")
            if progress is None and generation is not None and observed_generation is not None:
                progress = generation == observed_generation
            if isinstance(progress, bool):
                values = {"generation": generation, "observed_generation": observed_generation, "progressing": progress}
                facts.append(self._fact(step, context, "controller.progress", f"Controller progress for {subject_id} is {progress}.", subjects=[subject_id], value=values))
                facts.append(self._fact(step, context, f"controller.progress.{str(progress).lower()}", f"Controller for {subject_id} is {'converging' if progress else 'not converging'}.", subjects=[subject_id], value=progress))
                if not progress:
                    facts.append(self._fact(step, context, "controller.stalled", f"Observed generation for {subject_id} does not match desired generation.", subjects=[subject_id], value=values))
        return facts

    def _placement_state(self, step: CollectorPlanStep, context: EvidenceContext) -> list[EvidenceFact]:
        facts: list[EvidenceFact] = []
        for subject_id in self._subjects(step, context):
            entity = context.entities.get(subject_id)
            if entity is None:
                continue
            observed = entity.observed_state
            conditions = observed.get("conditions", {}) if isinstance(observed.get("conditions"), dict) else {}
            reasons = [str(item.get("reason")) for item in conditions.values() if isinstance(item, dict) and item.get("reason")]
            phase = observed.get("phase")
            unsatisfied = observed.get("unsatisfied_constraints") or []
            if not unsatisfied and phase == "Pending":
                unsatisfied = [reason for reason in reasons if reason]
            feasible = observed.get("placement_feasible")
            if feasible is None and unsatisfied:
                feasible = False
            value = {"phase": phase, "reasons": reasons, "unsatisfied_constraints": unsatisfied, "feasible": feasible}
            facts.append(self._fact(step, context, "placement.state", f"Placement state captured for {subject_id}.", subjects=[subject_id], value=value))
            if feasible is False or unsatisfied:
                facts.append(self._fact(step, context, "placement.unsatisfied_constraint", f"Placement constraints are unsatisfied for {subject_id}: {unsatisfied or reasons}.", subjects=[subject_id], value=unsatisfied or reasons))
            elif feasible is True:
                facts.append(self._fact(step, context, "placement.feasible", f"At least one valid placement exists for {subject_id}.", subjects=[subject_id], value=True))
        return facts

    def _capacity_state(self, step: CollectorPlanStep, context: EvidenceContext) -> list[EvidenceFact]:
        facts: list[EvidenceFact] = []
        for subject_id in self._subjects(step, context):
            entity = context.entities.get(subject_id)
            if entity is None:
                continue
            observed = entity.observed_state
            pressure: dict[str, Any] = {}
            conditions = observed.get("conditions", {}) if isinstance(observed.get("conditions"), dict) else {}
            for key, condition in conditions.items():
                if key.endswith("Pressure") and isinstance(condition, dict):
                    pressure[key] = condition.get("status")
            capacity = observed.get("capacity")
            allocatable = observed.get("allocatable")
            exhausted = observed.get("capacity_exhausted") is True or any(value is True for value in pressure.values())
            value = {"capacity": capacity, "allocatable": allocatable, "pressure": pressure, "exhausted": exhausted}
            facts.append(self._fact(step, context, "capacity.state", f"Capacity state captured for {subject_id}.", subjects=[subject_id], value=value))
            facts.append(self._fact(step, context, "capacity.exhausted" if exhausted else "capacity.sufficient", f"Capacity for {subject_id} is {'exhausted' if exhausted else 'not reported exhausted'}.", subjects=[subject_id], value=exhausted))
        return facts

    def _reference_state(self, step: CollectorPlanStep, context: EvidenceContext) -> list[EvidenceFact]:
        facts: list[EvidenceFact] = []
        relationship_types = {"references", "configured_by", "mounts", "binds", "uses_identity", "selects", "routes_to"}
        for subject_id in self._subjects(step, context):
            relevant = [item for item in context.topology.relationships if item.source_id == subject_id and item.relationship_type in relationship_types]
            missing = [item for item in relevant if item.target_id not in context.entities]
            value = {"relationships": [item.model_dump(mode="json") for item in relevant], "missing_targets": [item.target_id for item in missing]}
            facts.append(self._fact(step, context, "configuration.reference_state", f"{subject_id} has {len(relevant)} resolved reference relationships and {len(missing)} missing targets.", subjects=[subject_id, *[item.target_id for item in relevant]], value=value))
            facts.append(self._fact(step, context, "configuration.reference_missing" if missing else "configuration.reference_valid", f"Configuration references for {subject_id} are {'incomplete' if missing else 'resolved'}.", subjects=[subject_id], value=[item.target_id for item in missing]))
        return facts

    def _discovery_issues(self, step: CollectorPlanStep, context: EvidenceContext) -> list[EvidenceFact]:
        return [
            self._fact(step, context, "discovery.issue", issue.message, subjects=step.subject_ids, value=issue.model_dump(mode="json"), attributes={"severity": issue.severity, "resource_type": issue.resource_type})
            for issue in context.snapshot.issues
        ]

    def _permission_gaps(self, step: CollectorPlanStep, context: EvidenceContext) -> list[EvidenceFact]:
        facts: list[EvidenceFact] = []
        for gap in context.snapshot.permission_gaps:
            subjects = [str(gap.get("resource") or gap.get("subject") or item) for item in step.subject_ids[:1]] or step.subject_ids
            facts.append(self._fact(step, context, "authorization.permission_gap", f"Read-only collection encountered a permission gap: {gap}.", subjects=subjects, value=gap))
            facts.append(self._fact(step, context, "observability.permission_gap", f"Evidence is incomplete because access was denied: {gap}.", subjects=subjects, value=gap))
        return facts

    def _observability_quality(self, step: CollectorPlanStep, context: EvidenceContext) -> list[EvidenceFact]:
        gaps = len(context.snapshot.permission_gaps)
        issues = len([item for item in context.snapshot.issues if item.severity == "error"])
        incomplete = context.snapshot.status != "complete" or gaps > 0 or issues > 0
        value = {
            "snapshot_status": context.snapshot.status,
            "permission_gap_count": gaps,
            "error_issue_count": issues,
            "observation_count": len(context.snapshot.observations),
        }
        facts = [self._fact(step, context, "observability.quality", f"Evidence quality for snapshot {context.snapshot.snapshot_id} was evaluated.", subjects=step.subject_ids, value=value)]
        facts.append(self._fact(step, context, "observability.gap" if incomplete else "observability.complete", f"Evidence boundary is {'incomplete' if incomplete else 'complete'} for this investigation.", subjects=step.subject_ids, value=incomplete))
        return facts


def _fact_type_matches(required: str, provided: str) -> bool:
    if required == provided:
        return True
    if required.endswith(".*"):
        return provided.startswith(required[:-1])
    return provided.startswith(f"{required}.") or required.startswith(f"{provided}.")
