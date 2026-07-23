from __future__ import annotations

from dataclasses import dataclass

from kubeops_core.discovery import (
    DiscoveryCollector,
    DiscoveryRequest,
    FixtureDiscoverySource,
    KubectlDiscoverySource,
    SnapshotBuilder,
)
from kubeops_core.health import HealthAssessmentEngine
from kubeops_core.models.discovery import DiscoveryBundle, EnvironmentSnapshot
from kubeops_core.models.environment import AccessValidationResult, EnvironmentDefinition
from kubeops_core.models.health import OperationalProfileAssessment, OperationalProfileSpec
from kubeops_core.models.topology import TopologyGraph
from kubeops_core.topology import TopologyCompiler


@dataclass(frozen=True)
class CollectionResult:
    bundle: DiscoveryBundle
    topology: TopologyGraph
    snapshot: EnvironmentSnapshot
    assessments: list[OperationalProfileAssessment]


class EnvironmentIntelligenceService:
    """Framework-independent orchestration for Release 0.2 read-only intelligence."""

    def __init__(self) -> None:
        self._topology = TopologyCompiler()
        self._snapshot = SnapshotBuilder()
        self._health = HealthAssessmentEngine()

    @staticmethod
    def _source(environment: EnvironmentDefinition, method_id: str | None = None):
        method = environment.access_method(method_id)
        if method.method_type == "fixture":
            return FixtureDiscoverySource()
        return KubectlDiscoverySource()

    def validate(self, environment: EnvironmentDefinition, method_id: str | None = None) -> AccessValidationResult:
        return self._source(environment, method_id).validate(environment, method_id)

    def collect(
        self,
        environment: EnvironmentDefinition,
        *,
        method_id: str | None = None,
        resource_types: list[str] | None = None,
        profiles: list[OperationalProfileSpec] | None = None,
        history: list[EnvironmentSnapshot] | None = None,
    ) -> CollectionResult:
        source = self._source(environment, method_id)
        bundle = DiscoveryCollector(source).collect(
            environment,
            DiscoveryRequest(method_id=method_id, resource_types=resource_types),
        )
        provisional_topology = self._topology.compile_bundle(bundle)
        snapshot = self._snapshot.build(bundle, provisional_topology)
        topology = self._topology.compile_snapshot(snapshot)
        if topology.relationships != snapshot.relationships:
            snapshot = snapshot.model_copy(
                update={
                    "relationships": topology.relationships,
                    "collection_summary": {
                        **snapshot.collection_summary,
                        "compiled_relationship_count": len(topology.relationships),
                    },
                    "metadata": {
                        **snapshot.metadata,
                        "topology_graph_id": topology.graph_id,
                        "topology_warnings": topology.warnings,
                    },
                }
            )
        assessments = [
            self._health.assess(profile, snapshot, history=[*(history or []), snapshot])
            for profile in profiles or []
        ]
        return CollectionResult(bundle=bundle, topology=topology, snapshot=snapshot, assessments=assessments)
