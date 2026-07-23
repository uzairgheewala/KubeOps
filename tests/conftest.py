from __future__ import annotations

from pathlib import Path

import pytest

from kubeops_core.models import AccessMethodDefinition, EnvironmentDefinition
from kubeops_core.profiles import OperationalProfileRegistry
from kubeops_core.registry import ScenarioFamilyRegistry
from kubeops_core.scenarios import ScenarioCompiler


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture()
def registry(repo_root: Path) -> ScenarioFamilyRegistry:
    result = ScenarioFamilyRegistry()
    result.load_directory(repo_root / "scenarios" / "families")
    return result


@pytest.fixture()
def compiler(registry: ScenarioFamilyRegistry) -> ScenarioCompiler:
    return ScenarioCompiler(registry)


@pytest.fixture()
def profile_registry(repo_root: Path) -> OperationalProfileRegistry:
    result = OperationalProfileRegistry()
    result.load_directory(repo_root / "profiles")
    return result


@pytest.fixture()
def degraded_environment(repo_root: Path) -> EnvironmentDefinition:
    return EnvironmentDefinition(
        environment_id="test-kind",
        name="Test Kind",
        environment_class="development",
        provider="local",
        cluster_provider="kind",
        access_methods=[
            AccessMethodDefinition(
                method_id="fixture",
                method_type="fixture",
                fixture_path=str(repo_root / "lab" / "fixtures" / "kind-demo-degraded.v1.yaml"),
            )
        ],
        default_access_method_id="fixture",
        operational_profile_ids=["cluster-observable.v1", "local-development-usable.v1"],
    )


@pytest.fixture()
def healthy_environment(repo_root: Path) -> EnvironmentDefinition:
    return EnvironmentDefinition(
        environment_id="test-kind",
        name="Test Kind",
        environment_class="development",
        provider="local",
        cluster_provider="kind",
        access_methods=[
            AccessMethodDefinition(
                method_id="fixture",
                method_type="fixture",
                fixture_path=str(repo_root / "lab" / "fixtures" / "kind-demo-healthy.v1.yaml"),
            )
        ],
        default_access_method_id="fixture",
        operational_profile_ids=["cluster-observable.v1", "local-development-usable.v1"],
    )
