from kubeops_core.registry import build_builtin_catalog


def test_builtin_catalog_exposes_extension_surfaces() -> None:
    snapshot = build_builtin_catalog().snapshot()
    assert snapshot.counts["invariant_family"] >= 20
    assert snapshot.counts["disturbance_mechanism"] >= 10
    assert snapshot.counts["composition_operator"] == 5
    assert snapshot.counts["canonical_type"] >= 20
    assert any(entry.registry_key == "authentication" for entry in snapshot.entries)
