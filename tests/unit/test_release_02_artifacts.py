from __future__ import annotations

from kubeops_core.artifacts import FileArtifactStore, build_snapshot_artifacts
from kubeops_core.environments import EnvironmentIntelligenceService


def test_snapshot_artifacts_are_content_addressed(degraded_environment, profile_registry, tmp_path) -> None:
    result = EnvironmentIntelligenceService().collect(
        degraded_environment,
        profiles=[profile_registry.get("local-development-usable.v1")],
    )
    artifacts = build_snapshot_artifacts(result.bundle, result.snapshot, result.topology, result.assessments)
    assert {item.artifact_type for item in artifacts} >= {
        "raw_discovery_bundle",
        "environment_snapshot",
        "topology_graph",
        "profile_assessment",
        "snapshot_manifest",
    }
    store = FileArtifactStore(tmp_path)
    for artifact in artifacts:
        store.put(artifact)
        assert store.get(artifact.scope_id, artifact.artifact_id) == artifact
