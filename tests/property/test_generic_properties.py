from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, strategies as st

from kubeops_core.simulator import SimulationEngine


safe_id = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),
    min_size=2,
    max_size=12,
).filter(lambda value: value not in {"consumer", "provider"})


@given(consumer_id=safe_id, provider_id=safe_id)
def test_renaming_preserves_family_semantics(compiler, consumer_id: str, provider_id: str) -> None:
    if consumer_id == provider_id:
        return
    scenario = compiler.compile(
        "dependency.endpoint_unreachable.v1",
        {"consumer_id": consumer_id, "provider_id": provider_id},
    )
    run = SimulationEngine().run(scenario)
    assert run.family_id == "dependency.endpoint_unreachable.v1"
    assert set(run.final_summary["unhealthy_invariants"]) == {
        "provider.reachable",
        "consumer.serviceable",
    }
    relationship = scenario.relationships[0]
    assert relationship.source_id == consumer_id
    assert relationship.target_id == provider_id
