from __future__ import annotations

from pathlib import Path

import yaml

from kubeops_core.diagnosis import ScenarioDiagnosisEvaluator
from kubeops_core.models import DiagnosticExpectation
from kubeops_core.registry import ScenarioFamilyRegistry
from kubeops_core.scenarios import ScenarioCompiler
from kubeops_core.simulator import SimulationEngine


ROOT = Path(__file__).resolve().parents[2]


def test_declared_diagnostic_basis_matches_observation_aware_expectations() -> None:
    payload = yaml.safe_load(
        (ROOT / "diagnostics/evaluation/basis-expectations.v1.yaml").read_text(encoding="utf-8")
    )
    registry = ScenarioFamilyRegistry()
    registry.load_directory(ROOT / "scenarios" / "families")
    compiler = ScenarioCompiler(registry)
    engine = SimulationEngine()
    evaluator = ScenarioDiagnosisEvaluator()

    failures: list[str] = []
    for case in payload["cases"]:
        scenario = compiler.compile(
            case["family_id"],
            disturbance_id=case["disturbance_id"],
            observation_profile_id=case["observation_profile_id"],
        )
        result = evaluator.evaluate(
            scenario,
            engine.run(scenario),
            DiagnosticExpectation.model_validate(case["expectation"]),
        )
        if not result.passed:
            failures.append(f"{case['case_id']}: {result.failures}")

    assert not failures, "\n".join(failures)
