from kubeops_core.artifacts import FileArtifactStore, build_run_artifacts
from kubeops_core.simulator import SimulationEngine


def test_artifact_bundle_is_hashed_and_round_trips(compiler, tmp_path) -> None:
    scenario = compiler.compile("dependency.authentication_failure.v1")
    run = SimulationEngine().run(scenario)
    artifacts = build_run_artifacts(scenario, run)
    assert {artifact.artifact_type for artifact in artifacts} == {
        "scenario_instance",
        "timeline",
        "snapshot",
        "observation_set",
        "run_manifest",
    }
    assert all(len(artifact.payload_hash) == 64 for artifact in artifacts)

    store = FileArtifactStore(tmp_path)
    for artifact in artifacts:
        store.put(artifact)
        loaded = store.get(run.run_id, artifact.artifact_id)
        assert loaded == artifact
