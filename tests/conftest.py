from __future__ import annotations

from pathlib import Path

import pytest

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
