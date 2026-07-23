from __future__ import annotations

from dataclasses import replace
from typing import Iterable
from uuid import uuid4

from kubeops_core.health import HealthAssessmentEngine, ProfileCompiler
from kubeops_core.models.diagnosis import (
    EvidenceFact,
    IncidentInvestigation,
    IncidentTimelineEntry,
    ProbeRun,
)
from kubeops_core.models.discovery import EnvironmentSnapshot
from kubeops_core.models.health import OperationalProfileSpec
from kubeops_core.models.topology import TopologyGraph
from kubeops_core.topology import TopologyCompiler
from kubeops_core.util import utc_now_iso

from .catalog import DiagnosticCatalog, build_builtin_diagnostic_catalog
from .engine import DiagnosisCertificateBuilder, HypothesisEngine, SymptomDeriver
from .evidence import EvidenceContext, EvidenceExecutor, EvidencePlanner
from .probes import ProbePlanner


class InvestigationService:
    """Read-only orchestration for opening, refining, and sealing diagnoses."""

    def __init__(self, catalog: DiagnosticCatalog | None = None) -> None:
        self.catalog = catalog or build_builtin_diagnostic_catalog()
        self._health = HealthAssessmentEngine()
        self._compiler = ProfileCompiler()
        self._topology = TopologyCompiler()
        self._evidence_planner = EvidencePlanner(self.catalog)
        self._evidence_executor = EvidenceExecutor(self.catalog)
        self._symptoms = SymptomDeriver()
        self._hypotheses = HypothesisEngine(self.catalog)
        self._probes = ProbePlanner(self.catalog)
        self._certificates = DiagnosisCertificateBuilder()

    def open(
        self,
        snapshot: EnvironmentSnapshot,
        profile: OperationalProfileSpec,
        *,
        topology: TopologyGraph | None = None,
        history: list[EnvironmentSnapshot] | None = None,
        title: str | None = None,
        initial_symptom: str | None = None,
        evidence_budget: int | None = 5,
    ) -> IncidentInvestigation:
        topology = topology or self._topology.compile_snapshot(snapshot)
        assessment = self._health.assess(profile, snapshot, history)
        compiled = self._compiler.compile(profile, snapshot)
        created = utc_now_iso()
        incident_id = f"inc-{uuid4().hex[:12]}"

        seed_evidence: list[EvidenceFact] = []
        symptoms, seed_evidence = self._symptoms.derive(compiled, assessment, seed_evidence)
        affected_subjects = sorted({subject for item in symptoms for subject in item.subject_ids})
        baseline_intents = [
            self.catalog.intent("entity.current_state.v1").model_copy(update={"subject_ids": affected_subjects}),
            self.catalog.intent("dependency.path.v1").model_copy(update={"subject_ids": affected_subjects}),
            self.catalog.intent("observability.quality.v1").model_copy(update={"subject_ids": affected_subjects}),
        ]
        context = self._context(snapshot, topology, assessment)
        collection_plan = self._evidence_planner.plan(
            baseline_intents,
            context,
            incident_id=incident_id,
            existing_fact_types={item.fact_type for item in seed_evidence},
        )
        collector_results = self._evidence_executor.execute(collection_plan, context)
        evidence = _merge_evidence(seed_evidence, *(result.evidence for result in collector_results))
        symptoms, evidence = self._symptoms.derive(compiled, assessment, evidence)
        hypotheses, causal_edges = self._hypotheses.generate(symptoms, evidence, topology)
        probe_plan = self._probes.plan(
            incident_id,
            hypotheses,
            evidence,
            evidence_budget=evidence_budget,
        )
        certificate = self._certificates.build(
            incident_id,
            assessment.violated_invariant_ids,
            hypotheses,
            evidence,
            causal_edges,
        )
        status = _incident_status(certificate.status)
        timeline = [
            IncidentTimelineEntry(
                sequence=0,
                occurred_at_iso=created,
                event_type="incident.opened",
                title="Investigation opened from operational-profile assessment.",
                subject_ids=affected_subjects,
                details={
                    "snapshot_id": snapshot.snapshot_id,
                    "profile_id": profile.profile_id,
                    "violated_invariant_count": len(assessment.violated_invariant_ids),
                },
            ),
            IncidentTimelineEntry(
                sequence=1,
                occurred_at_iso=created,
                event_type="evidence.baseline_collected",
                title=f"Collected {len(evidence)} normalized evidence facts.",
                subject_ids=affected_subjects,
                details={
                    "plan_id": collection_plan.plan_id,
                    "collector_runs": [item.model_dump(mode="json") for item in collector_results],
                },
            ),
            IncidentTimelineEntry(
                sequence=2,
                occurred_at_iso=created,
                event_type="diagnosis.generated",
                title=f"Generated {len(hypotheses)} hypotheses and {len(causal_edges)} causal edges.",
                subject_ids=affected_subjects,
                details={"certificate_status": certificate.status, "confidence": certificate.confidence},
            ),
        ]
        return IncidentInvestigation(
            incident_id=incident_id,
            environment_id=snapshot.environment_id,
            snapshot_id=snapshot.snapshot_id,
            profile_id=profile.profile_id,
            title=title or f"{profile.title}: {snapshot.environment_id}",
            initial_symptom=initial_symptom or _initial_symptom(symptoms),
            status=status,
            created_at_iso=created,
            updated_at_iso=created,
            assessment_id=assessment.assessment_id,
            violated_invariant_ids=assessment.violated_invariant_ids,
            symptoms=symptoms,
            evidence=evidence,
            hypotheses=hypotheses,
            probe_plan=probe_plan,
            causal_edges=causal_edges,
            timeline=timeline,
            certificate=certificate,
            metadata={
                "profile_assessment": assessment.model_dump(mode="json"),
                "compiled_profile_hash": compiled.content_hash,
                "topology_graph_id": topology.graph_id,
                "baseline_collection_plan": collection_plan.model_dump(mode="json"),
            },
        )

    def run_probe(
        self,
        incident: IncidentInvestigation,
        probe_id: str,
        snapshot: EnvironmentSnapshot,
        profile: OperationalProfileSpec,
        *,
        topology: TopologyGraph | None = None,
        history: list[EnvironmentSnapshot] | None = None,
        evidence_budget: int | None = 5,
    ) -> IncidentInvestigation:
        if incident.probe_plan is None:
            raise ValueError("incident has no probe plan")
        probe = next((item for item in incident.probe_plan.probes if item.probe_id == probe_id), None)
        if probe is None:
            raise KeyError(f"unknown probe {probe_id}")
        topology = topology or self._topology.compile_snapshot(snapshot)
        assessment = self._health.assess(profile, snapshot, history)
        compiled = self._compiler.compile(profile, snapshot)
        context = self._context(snapshot, topology, assessment)
        intent = self.catalog.intent(probe.evidence_intent_id).model_copy(
            update={
                "subject_ids": list(probe.metadata.get("subject_ids", [])),
                "preferred_collector_ids": probe.candidate_collector_ids,
                "required_fact_types": list(probe.metadata.get("missing_fact_types", [])),
            }
        )
        collection_plan = self._evidence_planner.plan(
            [intent],
            context,
            incident_id=incident.incident_id,
            existing_fact_types={item.fact_type for item in incident.evidence},
        )
        started = utc_now_iso()
        collector_results = self._evidence_executor.execute(collection_plan, context)
        evidence = _merge_evidence(incident.evidence, *(result.evidence for result in collector_results))
        symptoms, evidence = self._symptoms.derive(compiled, assessment, evidence)
        hypotheses, causal_edges = self._hypotheses.generate(symptoms, evidence, topology)
        previous = {item.family_id: item for item in incident.hypotheses}
        changes = {
            item.family_id: {
                "before_status": previous[item.family_id].status if item.family_id in previous else None,
                "after_status": item.status,
                "before_confidence": previous[item.family_id].confidence if item.family_id in previous else None,
                "after_confidence": item.confidence,
            }
            for item in hypotheses
            if item.family_id not in previous
            or previous[item.family_id].status != item.status
            or previous[item.family_id].confidence != item.confidence
        }
        probe_run = ProbeRun(
            probe_run_id=f"probe-run-{uuid4().hex[:12]}",
            incident_id=incident.incident_id,
            probe=probe.model_copy(update={"status": "completed"}),
            collection_plan=collection_plan,
            collector_results=collector_results,
            evidence_ids=[item.evidence_id for result in collector_results for item in result.evidence],
            status=(
                "completed"
                if collector_results and all(item.status == "completed" for item in collector_results)
                else "partial"
            ),
            started_at_iso=started,
            completed_at_iso=utc_now_iso(),
            hypothesis_changes=changes,
        )
        next_probe_plan = self._probes.plan(
            incident.incident_id,
            hypotheses,
            evidence,
            evidence_budget=evidence_budget,
        )
        certificate = self._certificates.build(
            incident.incident_id,
            assessment.violated_invariant_ids,
            hypotheses,
            evidence,
            causal_edges,
        )
        now = utc_now_iso()
        timeline = [
            *incident.timeline,
            IncidentTimelineEntry(
                sequence=len(incident.timeline),
                occurred_at_iso=now,
                event_type="probe.completed",
                title=f"Completed probe: {probe.title}",
                subject_ids=list(probe.metadata.get("subject_ids", [])),
                details={
                    "probe_run_id": probe_run.probe_run_id,
                    "new_evidence_count": len(probe_run.evidence_ids),
                    "hypothesis_changes": changes,
                },
            ),
            IncidentTimelineEntry(
                sequence=len(incident.timeline) + 1,
                occurred_at_iso=now,
                event_type="diagnosis.refined",
                title=f"Diagnosis refined to {certificate.status}.",
                subject_ids=list(probe.metadata.get("subject_ids", [])),
                details={"confidence": certificate.confidence},
            ),
        ]
        return incident.model_copy(
            update={
                "status": _incident_status(certificate.status),
                "updated_at_iso": now,
                "symptoms": symptoms,
                "evidence": evidence,
                "hypotheses": hypotheses,
                "probe_plan": next_probe_plan,
                "probe_runs": [*incident.probe_runs, probe_run],
                "causal_edges": causal_edges,
                "timeline": timeline,
                "certificate": certificate,
            }
        )

    @staticmethod
    def _context(
        snapshot: EnvironmentSnapshot,
        topology: TopologyGraph,
        assessment: object,
    ) -> EvidenceContext:
        return EvidenceContext(
            snapshot=snapshot,
            topology=topology,
            assessments=(assessment,),  # type: ignore[arg-type]
            mode=snapshot.source_type,
            available_capabilities=frozenset({"snapshot", "topology"}),
        )


def _merge_evidence(*groups: Iterable[EvidenceFact]) -> list[EvidenceFact]:
    by_id: dict[str, EvidenceFact] = {}
    for group in groups:
        for item in group:
            by_id[item.evidence_id] = item
    return sorted(by_id.values(), key=lambda item: item.evidence_id)


def _incident_status(certificate_status: str) -> str:
    if certificate_status in {"root_cause_identified", "failure_class_identified"}:
        return "diagnosed"
    if certificate_status in {"insufficient_evidence", "unknown_semantics"}:
        return "insufficient_evidence"
    return "investigating"


def _initial_symptom(symptoms: list[object]) -> str:
    if not symptoms:
        return "No violated or unknown operational invariants were detected."
    first = symptoms[0]
    return str(getattr(first, "statement", "Operational-profile assessment is not healthy."))
