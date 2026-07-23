"""KubeOps Release 0.4 guarded lifecycle and recovery core package."""

from .discovery import DiscoveryCollector, FixtureDiscoverySource, KubectlDiscoverySource
from .environments import EnvironmentIntelligenceService
from .health import HealthAssessmentEngine, ProfileCompiler
from .diagnosis import InvestigationService, ScenarioDiagnosisEvaluator
from .actions import ActionCatalog, build_builtin_action_catalog
from .execution import OperationRuntime
from .lifecycle import LifecyclePlanner, LifecycleProfileRegistry
from .policy import PolicyEngine
from .verification import VerificationEngine
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

__version__ = "0.4.0"
