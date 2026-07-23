"""KubeOps Release 0.2 core package."""

from .discovery import DiscoveryCollector, FixtureDiscoverySource, KubectlDiscoverySource
from .environments import EnvironmentIntelligenceService
from .health import HealthAssessmentEngine, ProfileCompiler
from .models import (
    EnvironmentDefinition,
    EnvironmentSnapshot,
    InvariantDefinition,
    OperationalEntity,
    OperationalProfileAssessment,
    Relationship,
    ScenarioFamily,
    ScenarioInstance,
    SnapshotDiff,
    TopologyGraph,
)
from .scenarios.compiler import ScenarioCompiler
from .scenarios.composer import ScenarioComposer
from .simulator.engine import SimulationEngine
from .topology import TopologyCompiler

__all__ = [name for name in globals() if not name.startswith("_")]

__version__ = "0.2.0"
