import pytest

from kubeops_core.scenarios import ScenarioCompileError


def test_child_family_inherits_topology_and_parameters(compiler) -> None:
    effective = compiler.effective_family("dependency.endpoint_unreachable.v1")
    parameter_names = {parameter.name for parameter in effective.parameters}
    assert {"consumer_id", "provider_id", "failure_layer"} <= parameter_names

    scenario = compiler.compile(
        "dependency.endpoint_unreachable.v1",
        {
            "consumer_id": "worker",
            "consumer_name": "Worker",
            "provider_id": "kubernetes-api",
            "provider_name": "Kubernetes API",
            "failure_layer": "tls",
        },
    )
    assert {entity.entity_id for entity in scenario.entities} == {"worker", "kubernetes-api"}
    assert scenario.relationships[0].source_id == "worker"
    assert scenario.relationships[0].target_id == "kubernetes-api"
    assert scenario.disturbance.mutations[0].mutation.value == "tls"


def test_same_family_compiles_to_materially_different_instances(compiler) -> None:
    k8s = compiler.compile(
        "dependency.authentication_failure.v1",
        {"consumer_name": "Builder", "provider_name": "Kubernetes API"},
    )
    registry = compiler.compile(
        "dependency.authentication_failure.v1",
        {
            "consumer_name": "Kubelet",
            "provider_name": "Private registry",
            "provider_type": "external_service",
        },
    )
    assert k8s.family_id == registry.family_id
    assert k8s.title != registry.title
    assert k8s.content_hash != registry.content_hash


def test_semantic_constraint_rejects_self_dependency(compiler) -> None:
    with pytest.raises(ScenarioCompileError, match="distinct"):
        compiler.compile(
            "dependency.endpoint_unreachable.v1",
            {"consumer_id": "same", "provider_id": "same"},
        )
