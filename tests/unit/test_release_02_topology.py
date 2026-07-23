from __future__ import annotations

from kubeops_core.environments import EnvironmentIntelligenceService


def test_topology_compiles_cross_resource_edges(degraded_environment) -> None:
    result = EnvironmentIntelligenceService().collect(degraded_environment)
    relationship_types = {item.relationship_type for item in result.snapshot.relationships}
    assert {
        "controls",
        "scheduled_on",
        "uses_identity",
        "references_config",
        "references_secret",
        "mounts_claim",
        "selects",
        "publishes_endpoints",
        "routes_to",
        "binds_to",
        "uses_storage_class",
        "grants_role",
        "binds_subject",
    } - relationship_types == set()

    ingress_id = "k8s/ingress/demo/web"
    service_id = "k8s/service/demo/web"
    assert any(
        edge.source_id == ingress_id and edge.target_id == service_id and edge.relationship_type == "routes_to"
        for edge in result.snapshot.relationships
    )
