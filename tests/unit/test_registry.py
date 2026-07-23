def test_registry_loads_release_01_family_basis(registry) -> None:
    assert set(registry.keys()) == {
        "controller.convergence_failure.v1",
        "dependency.authentication_failure.v1",
        "dependency.endpoint_unreachable.v1",
        "dependency.failure.v1",
        "entity.required_absent.v1",
    }


def test_family_lineage_is_resolved(registry) -> None:
    lineage = registry.lineage("dependency.authentication_failure.v1")
    assert [item.family_id for item in lineage] == [
        "dependency.failure.v1",
        "dependency.authentication_failure.v1",
    ]
