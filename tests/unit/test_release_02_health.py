from __future__ import annotations

from kubeops_core.environments import EnvironmentIntelligenceService


def test_profiles_distinguish_observability_from_serviceability(degraded_environment, profile_registry) -> None:
    profiles = [profile_registry.get(profile_id) for profile_id in degraded_environment.operational_profile_ids]
    result = EnvironmentIntelligenceService().collect(degraded_environment, profiles=profiles)
    assessments = {item.profile_id: item for item in result.assessments}
    assert assessments["cluster-observable.v1"].status == "healthy"
    usable = assessments["local-development-usable.v1"]
    assert usable.status == "unhealthy"
    assert any("workload.available" in item for item in usable.violated_invariant_ids)
    assert any("pod.ready" in item for item in usable.violated_invariant_ids)


def test_healthy_fixture_satisfies_required_local_profile(healthy_environment, profile_registry) -> None:
    profile = profile_registry.get("local-development-usable.v1")
    result = EnvironmentIntelligenceService().collect(healthy_environment, profiles=[profile])
    assessment = result.assessments[0]
    assert assessment.status in {"healthy", "degraded"}
    assert not [item for item in assessment.violated_invariant_ids if "workload.available" in item]
