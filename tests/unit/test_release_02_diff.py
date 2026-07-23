from __future__ import annotations

from kubeops_core.discovery import diff_snapshots
from kubeops_core.environments import EnvironmentIntelligenceService


def test_snapshot_diff_identifies_readiness_recovery(degraded_environment, healthy_environment) -> None:
    service = EnvironmentIntelligenceService()
    before = service.collect(degraded_environment).snapshot
    after = service.collect(healthy_environment).snapshot
    result = diff_snapshots(before, after)
    changed = {item.entity_id: item for item in result.entity_changes}
    assert "k8s/deployment/demo/web" in changed
    assert "k8s/pod/demo/web-abc-2" in changed
    paths = {item.path for item in changed["k8s/pod/demo/web-abc-2"].field_changes}
    assert "observed_state.ready" in paths
    assert result.summary["entities_changed"] >= 2
