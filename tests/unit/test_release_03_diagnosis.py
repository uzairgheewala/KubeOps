from __future__ import annotations

from pathlib import Path

import yaml

from kubeops_core.diagnosis import (
    EvidenceContext,
    EvidencePlanner,
    HypothesisEngine,
    InvestigationService,
    build_builtin_diagnostic_catalog,
)
from kubeops_core.environments import EnvironmentIntelligenceService
from kubeops_core.models import EnvironmentDefinition, EvidenceFact, Symptom
from kubeops_core.models.enums import InvariantFamily
from kubeops_core.profiles import OperationalProfileRegistry


ROOT = Path(__file__).resolve().parents[2]


def _fixture():
    environment = EnvironmentDefinition.model_validate(
        yaml.safe_load((ROOT / "environments/demo-kind-fixture.v1.yaml").read_text())
    )
    result = EnvironmentIntelligenceService().collect(environment)
    profiles = OperationalProfileRegistry()
    profiles.load_directory(ROOT / "profiles")
    return result, profiles.get("local-development-usable.v1")


def test_catalog_exposes_read_only_diagnostic_extensions() -> None:
    catalog = build_builtin_diagnostic_catalog()
    assert len(catalog.intents()) >= 10
    assert len(catalog.collectors()) >= 13
    assert len(catalog.templates()) >= 10
    assert all(item.risk_class == "R0" for item in catalog.collectors())


def test_incident_opening_preserves_uncertainty_and_recommends_discriminative_probe() -> None:
    result, profile = _fixture()
    incident = InvestigationService().open(result.snapshot, profile, topology=result.topology)
    assert incident.violated_invariant_ids
    assert incident.symptoms
    assert incident.evidence
    assert incident.hypotheses
    assert incident.certificate is not None
    assert incident.certificate.status in {
        "root_cause_identified",
        "failure_class_identified",
        "multiple_plausible_causes",
        "partial_causal_chain",
    }
    assert incident.probe_plan is not None
    assert incident.probe_plan.probes
    first = incident.probe_plan.probes[0]
    assert first.risk_class == "R0"
    assert "snapshot.conditions.v1" in first.candidate_collector_ids


def test_probe_run_adds_evidence_and_refines_hypotheses() -> None:
    result, profile = _fixture()
    service = InvestigationService()
    incident = service.open(result.snapshot, profile, topology=result.topology)
    probe = incident.probe_plan.probes[0]  # type: ignore[union-attr]
    refined = service.run_probe(
        incident,
        probe.probe_id,
        result.snapshot,
        profile,
        topology=result.topology,
    )
    assert len(refined.evidence) > len(incident.evidence)
    assert len(refined.probe_runs) == 1
    assert any(item.event_type == "probe.completed" for item in refined.timeline)
    assert refined.certificate is not None


def test_contradictory_authoritative_evidence_rules_out_authentication_hypothesis() -> None:
    catalog = build_builtin_diagnostic_catalog()
    symptom = Symptom(
        symptom_id="sym-auth",
        symptom_type="invariant.authentication.violated",
        statement="authentication invariant failed",
        subject_ids=["worker"],
        invariant_family=InvariantFamily.AUTHENTICATION,
    )
    evidence = [
        EvidenceFact(
            evidence_id="ev-success",
            fact_type="authentication.state.succeeded",
            statement="request authenticated",
            value=True,
            subject_ids=["worker"],
            collector_id="test",
            observed_at_iso="2026-01-01T00:00:00+00:00",
            authority="authoritative",
        )
    ]
    from kubeops_core.models import TopologyGraph

    hypotheses, _ = HypothesisEngine(catalog).generate(
        [symptom], evidence, TopologyGraph(graph_id="g", environment_id="e", snapshot_id="s", generated_at_iso="2026-01-01T00:00:00+00:00")
    )
    auth = next(item for item in hypotheses if item.family_id == "dependency.authentication_failure")
    assert auth.status == "ruled_out"
    assert auth.contradicting_evidence_ids == ["ev-success"]


def test_evidence_planner_never_selects_mutating_collector() -> None:
    result, _ = _fixture()
    catalog = build_builtin_diagnostic_catalog()
    intent = catalog.intent("endpoint.layer.v1").model_copy(
        update={"subject_ids": ["k8s/service/demo/web"]}
    )
    plan = EvidencePlanner(catalog).plan(
        [intent],
        EvidenceContext(
            snapshot=result.snapshot,
            topology=result.topology,
            mode="fixture",
            available_capabilities=frozenset({"snapshot", "topology"}),
        ),
    )
    assert plan.steps
    assert all(catalog.collector(item.collector_id).risk_class == "R0" for item in plan.steps)
