from __future__ import annotations

from collections import Counter
from uuid import uuid4

from kubeops_core.models.diagnosis import (
    DiagnosticCaseResult,
    DiagnosticEvaluationReport,
    DiagnosticExpectation,
    EvidenceFact,
    IncidentInvestigation,
)
from kubeops_core.models.enums import HealthStatus
from kubeops_core.models.health import CompiledOperationalProfile, OperationalProfileAssessment
from kubeops_core.models.run import SimulationRun
from kubeops_core.models.scenario import ScenarioInstance
from kubeops_core.models.topology import TopologyGraph
from kubeops_core.util import utc_now_iso

from .catalog import DiagnosticCatalog, build_builtin_diagnostic_catalog
from .engine import DiagnosisCertificateBuilder, HypothesisEngine, SymptomDeriver
from .probes import ProbePlanner


class ScenarioDiagnosisEvaluator:
    """Evaluate deterministic diagnosis directly against Release 0.1 simulations."""

    def __init__(self, catalog: DiagnosticCatalog | None = None) -> None:
        self.catalog = catalog or build_builtin_diagnostic_catalog()
        self._symptoms = SymptomDeriver()
        self._hypotheses = HypothesisEngine(self.catalog)
        self._probes = ProbePlanner(self.catalog)
        self._certificates = DiagnosisCertificateBuilder()

    def evaluate(
        self,
        scenario: ScenarioInstance,
        run: SimulationRun,
        expectation: DiagnosticExpectation,
    ) -> DiagnosticCaseResult:
        final = run.snapshots[-1]
        assessment = OperationalProfileAssessment(
            assessment_id=f"assessment-{run.run_id}",
            profile_id="simulation-final-state",
            profile_version="1.0.0",
            environment_id=scenario.scenario_id,
            snapshot_id=run.run_id,
            evaluated_at_iso=run.completed_at_iso or run.started_at_iso,
            status=(
                HealthStatus.UNHEALTHY
                if any(item.status == HealthStatus.UNHEALTHY for item in final.invariant_evaluations)
                else HealthStatus.UNKNOWN
                if any(item.status == HealthStatus.UNKNOWN for item in final.invariant_evaluations)
                else HealthStatus.HEALTHY
            ),
            evaluations=final.invariant_evaluations,
            required_invariant_ids=[item.invariant_id for item in scenario.invariants],
            violated_invariant_ids=[item.invariant_id for item in final.invariant_evaluations if item.status == HealthStatus.UNHEALTHY],
            unknown_invariant_ids=[item.invariant_id for item in final.invariant_evaluations if item.status == HealthStatus.UNKNOWN],
            counts=dict(Counter(str(item.status) for item in final.invariant_evaluations)),
        )
        compiled = CompiledOperationalProfile(
            profile_id="simulation-final-state",
            version="1.0.0",
            environment_id=scenario.scenario_id,
            snapshot_id=run.run_id,
            compiled_at_iso=run.completed_at_iso or run.started_at_iso,
            invariants=scenario.invariants,
            required_invariant_ids=[item.invariant_id for item in scenario.invariants],
        )
        evidence = self._simulation_evidence(scenario, run)
        symptoms, evidence = self._symptoms.derive(compiled, assessment, evidence)
        topology = TopologyGraph(
            graph_id=f"sim-topology-{run.run_id}",
            environment_id=scenario.scenario_id,
            snapshot_id=run.run_id,
            generated_at_iso=run.completed_at_iso or run.started_at_iso,
            entities=scenario.entities,
            relationships=scenario.relationships,
        )
        hypotheses, edges = self._hypotheses.generate(symptoms, evidence, topology)
        probes = self._probes.plan(run.run_id, hypotheses, evidence)
        certificate = self._certificates.build(
            run.run_id,
            assessment.violated_invariant_ids,
            hypotheses,
            evidence,
            edges,
        )
        predicted = {item.family_id for item in hypotheses if item.status in {"proven", "supported"} and not item.metadata.get("generic")}
        failures: list[str] = []
        if expectation.expected_family_ids and not (predicted & expectation.expected_family_ids):
            if not (predicted & expectation.acceptable_parent_family_ids):
                failures.append(
                    f"expected one of {sorted(expectation.expected_family_ids)}, predicted {sorted(predicted)}"
                )
        forbidden = predicted & expectation.forbidden_family_ids
        if forbidden:
            failures.append(f"predicted forbidden families {sorted(forbidden)}")
        if expectation.required_statuses and certificate.status not in expectation.required_statuses:
            failures.append(
                f"certificate status {certificate.status} not in {sorted(expectation.required_statuses)}"
            )
        if expectation.maximum_probe_count is not None and len(probes.probes) > expectation.maximum_probe_count:
            failures.append(
                f"probe count {len(probes.probes)} exceeds {expectation.maximum_probe_count}"
            )
        precision = len(predicted & expectation.expected_family_ids) / max(len(predicted), 1)
        recall = len(predicted & expectation.expected_family_ids) / max(len(expectation.expected_family_ids), 1)
        incident = IncidentInvestigation(
            incident_id=run.run_id,
            environment_id=scenario.scenario_id,
            snapshot_id=run.run_id,
            profile_id="simulation-final-state",
            title=scenario.title,
            initial_symptom=symptoms[0].statement if symptoms else "No unhealthy invariant",
            status="diagnosed" if certificate.status in {"root_cause_identified", "failure_class_identified"} else "investigating",
            created_at_iso=run.started_at_iso,
            updated_at_iso=run.completed_at_iso or run.started_at_iso,
            assessment_id=assessment.assessment_id,
            violated_invariant_ids=assessment.violated_invariant_ids,
            symptoms=symptoms,
            evidence=evidence,
            hypotheses=hypotheses,
            probe_plan=probes,
            causal_edges=edges,
            certificate=certificate,
        )
        return DiagnosticCaseResult(
            case_id=f"case-{uuid4().hex[:12]}",
            scenario_id=scenario.scenario_id,
            passed=not failures,
            certificate_status=certificate.status,
            predicted_family_ids=sorted(predicted),
            expected_family_ids=sorted(expectation.expected_family_ids),
            probe_count=len(probes.probes),
            metrics={"precision": round(precision, 4), "recall": round(recall, 4), "confidence": certificate.confidence},
            failures=failures,
            incident=incident,
        )

    @staticmethod
    def report(results: list[DiagnosticCaseResult]) -> DiagnosticEvaluationReport:
        passed = sum(item.passed for item in results)
        families = Counter(family for item in results for family in item.predicted_family_ids)
        return DiagnosticEvaluationReport(
            report_id=f"diag-report-{uuid4().hex[:12]}",
            created_at_iso=utc_now_iso(),
            case_results=results,
            metrics={
                "case_count": float(len(results)),
                "pass_rate": round(passed / max(len(results), 1), 4),
                "mean_precision": round(sum(item.metrics.get("precision", 0.0) for item in results) / max(len(results), 1), 4),
                "mean_recall": round(sum(item.metrics.get("recall", 0.0) for item in results) / max(len(results), 1), 4),
                "mean_probe_count": round(sum(item.probe_count for item in results) / max(len(results), 1), 4),
            },
            coverage={"predicted_families": dict(sorted(families.items()))},
        )

    @staticmethod
    def _simulation_evidence(scenario: ScenarioInstance, run: SimulationRun) -> list[EvidenceFact]:
        final = run.snapshots[-1]
        facts: list[EvidenceFact] = []
        for entity_id, state in final.observed_state.items():
            observed = state.get("observed_state", state)
            for field in ["exists", "ready", "serviceable", "reachable", "authenticated", "authorized"]:
                value = observed.get(field) if isinstance(observed, dict) else None
                if isinstance(value, bool):
                    facts.append(
                        EvidenceFact(
                            evidence_id=f"sim-{run.run_id}-{entity_id.replace('/', '_')}-{field}",
                            fact_type=f"entity.{field}.{str(value).lower()}",
                            statement=f"Simulation reports {entity_id}.{field}={value}.",
                            value=value,
                            subject_ids=[entity_id],
                            collector_id="simulation.final_state.v1",
                            observed_at_iso=run.completed_at_iso or run.started_at_iso,
                            authority="authoritative",
                        )
                    )
            failed_layer = observed.get("failed_layer") if isinstance(observed, dict) else None
            if failed_layer:
                facts.append(
                    EvidenceFact(
                        evidence_id=f"sim-{run.run_id}-{entity_id.replace('/', '_')}-layer",
                        fact_type="endpoint.layer",
                        statement=f"Simulation localizes endpoint failure to {failed_layer}.",
                        value=failed_layer,
                        subject_ids=[entity_id],
                        collector_id="simulation.final_state.v1",
                        observed_at_iso=run.completed_at_iso or run.started_at_iso,
                        authority="authoritative",
                    )
                )
        return facts
