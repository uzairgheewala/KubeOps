from __future__ import annotations

from kubeops_core.environments import EnvironmentIntelligenceService


def test_fixture_access_validation_and_collection(degraded_environment, profile_registry) -> None:
    service = EnvironmentIntelligenceService()
    validation = service.validate(degraded_environment)
    assert validation.status == "healthy"
    assert "fixture_replay" in validation.capabilities

    result = service.collect(
        degraded_environment,
        profiles=[profile_registry.get(profile_id) for profile_id in degraded_environment.operational_profile_ids],
    )
    assert result.snapshot.status == "complete"
    assert len(result.snapshot.entities) == 26
    assert len(result.snapshot.relationships) >= 25
    assert result.topology.statistics["entity_kinds"]["Pod"] == 3
    assert result.topology.statistics["relationship_types"]["scheduled_on"] == 3


def test_secret_values_are_redacted(degraded_environment) -> None:
    result = EnvironmentIntelligenceService().collect(degraded_environment)
    secret = next(entity for entity in result.snapshot.entities if entity.entity_type == "kubernetes.secret")
    resource = secret.extensions["kubernetes"]["sanitized_resource"]
    assert "data" not in resource
    assert resource["redaction"]["data_keys"] == ["DATABASE_PASSWORD"]
    assert resource["redaction"]["values_removed"] is True


def test_discovery_fixture_export_round_trips_sanitized_resources(degraded_environment):
    from kubeops_core.discovery import FixtureDiscoverySource, export_discovery_fixture
    from kubeops_core.discovery.collector import DiscoveryCollector

    bundle = DiscoveryCollector(FixtureDiscoverySource()).collect(degraded_environment)
    exported = export_discovery_fixture(bundle, snapshot_id="snapshot:test")

    assert exported["api_version"] == "kubeops.io/discovery-fixture/v1"
    assert exported["metadata"]["exported_from_snapshot_id"] == "snapshot:test"
    assert exported["resources"]
    serialized = __import__("json").dumps(exported)
    assert "super-secret-password" not in serialized
    assert "DATABASE_PASSWORD" in serialized
