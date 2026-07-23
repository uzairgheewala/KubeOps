from __future__ import annotations

from pathlib import Path

import yaml

from kubeops_core.artifacts import FileArtifactStore, build_incident_artifacts
from kubeops_core.diagnosis import InvestigationService
from kubeops_core.environments import EnvironmentIntelligenceService
from kubeops_core.models import EnvironmentDefinition
from kubeops_core.profiles import OperationalProfileRegistry


ROOT = Path(__file__).resolve().parents[2]


def test_incident_artifacts_are_content_addressed_and_replayable(tmp_path: Path) -> None:
    environment = EnvironmentDefinition.model_validate(
        yaml.safe_load((ROOT / "environments/demo-kind-fixture.v1.yaml").read_text())
    )
    result = EnvironmentIntelligenceService().collect(environment)
    profiles = OperationalProfileRegistry()
    profiles.load_directory(ROOT / "profiles")
    incident = InvestigationService().open(
        result.snapshot,
        profiles.get("local-development-usable.v1"),
        topology=result.topology,
    )
    artifacts = build_incident_artifacts(incident)
    assert artifacts[-1].artifact_type == "incident_manifest"
    assert len({item.artifact_id for item in artifacts}) == len(artifacts)
    store = FileArtifactStore(tmp_path)
    for artifact in artifacts:
        path = store.put(artifact)
        assert path.exists()
        assert store.get(incident.incident_id, artifact.artifact_id).content_hash == artifact.content_hash
