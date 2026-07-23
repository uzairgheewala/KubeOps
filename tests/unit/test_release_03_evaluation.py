from __future__ import annotations

from pathlib import Path

from kubeops_core.diagnosis import ScenarioDiagnosisEvaluator
from kubeops_core.models import DiagnosticExpectation
from kubeops_core.registry import ScenarioFamilyRegistry
from kubeops_core.scenarios import ScenarioCompiler
from kubeops_core.simulator import SimulationEngine


ROOT = Path(__file__).resolve().parents[2]


def test_simulated_reachability_scenario_maps_to_generic_diagnostic_family() -> None:
    registry = ScenarioFamilyRegistry()
    registry.load_directory(ROOT / "scenarios/families")
    scenario = ScenarioCompiler(registry).compile(
        "dependency.endpoint_unreachable.v1",
        bindings={
            "consumer_id": "consumer",
            "consumer_name": "consumer",
            "provider_id": "provider",
            "provider_name": "provider",
            "dependency_kind": "requires_for_service",
            "failure_layer": "transport",
        },
    )
    run = SimulationEngine().run(scenario)
    result = ScenarioDiagnosisEvaluator().evaluate(
        scenario,
        run,
        DiagnosticExpectation(
            expected_family_ids={"dependency.endpoint_unreachable"},
            required_statuses={"root_cause_identified", "failure_class_identified", "multiple_plausible_causes"},
            maximum_probe_count=5,
        ),
    )
    assert result.passed, result.failures
    assert "dependency.endpoint_unreachable" in result.predicted_family_ids


def test_report_summarizes_case_coverage() -> None:
    evaluator = ScenarioDiagnosisEvaluator()
    report = evaluator.report([])
    assert report.metrics["case_count"] == 0.0
    assert report.metrics["pass_rate"] == 0.0
