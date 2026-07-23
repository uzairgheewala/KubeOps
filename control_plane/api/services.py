from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from django.conf import settings

from kubeops_core.artifacts import FileArtifactStore
from kubeops_core.models.registry import RegistryEntry
from kubeops_core.registry import ScenarioFamilyRegistry, build_builtin_catalog
from kubeops_core.scenarios import ScenarioCompiler
from kubeops_core.simulator import SimulationEngine


@lru_cache(maxsize=1)
def scenario_registry() -> ScenarioFamilyRegistry:
    registry = ScenarioFamilyRegistry()
    registry.load_directory(Path(settings.KUBEOPS_SCENARIO_DIR) / "families")
    return registry




@lru_cache(maxsize=1)
def registry_catalog():
    catalog = build_builtin_catalog()
    for family in scenario_registry().values():
        catalog.register(
            RegistryEntry(
                registry_key=family.family_id,
                category="scenario_family",
                version=family.version,
                title=family.title,
                description=family.description,
                capabilities={"compile"} if not family.abstract else {"inherit"},
                metadata={
                    "parent_family_id": family.parent_family_id,
                    "abstract": family.abstract,
                    "content_hash": family.content_hash,
                },
            )
        )
    return catalog


@lru_cache(maxsize=1)
def scenario_compiler() -> ScenarioCompiler:
    return ScenarioCompiler(scenario_registry())


@lru_cache(maxsize=1)
def simulation_engine() -> SimulationEngine:
    return SimulationEngine()


@lru_cache(maxsize=1)
def artifact_store() -> FileArtifactStore:
    return FileArtifactStore(settings.KUBEOPS_ARTIFACT_DIR)


def clear_service_caches() -> None:
    scenario_registry.cache_clear()
    scenario_compiler.cache_clear()
    registry_catalog.cache_clear()
    simulation_engine.cache_clear()
    artifact_store.cache_clear()
