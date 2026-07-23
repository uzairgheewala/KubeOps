from kubeops_core.invariants import InvariantEngine
from kubeops_core.models.invariant import InvariantDefinition, TemporalRequirement


def world(ready: bool):
    return {
        "api": {
            "entity_id": "api",
            "observed_state": {"ready": ready},
        }
    }


def invariant(temporal: TemporalRequirement):
    return InvariantDefinition(
        invariant_id="api.ready",
        title="API is ready",
        family="readiness",
        subject_id="api",
        predicate={
            "predicate_type": "field_equals",
            "entity_id": "api",
            "path": "observed_state.ready",
            "value": True,
        },
        temporal=temporal,
    )


def test_eventually_is_pending_before_deadline_and_unhealthy_after() -> None:
    engine = InvariantEngine()
    definition = invariant(TemporalRequirement(operator="eventually", within_seconds=5))
    pending = engine.evaluate_all([definition], world(False), 3)[0]
    failed = engine.evaluate_all([definition], world(False), 5)[0]
    assert pending.status == "pending"
    assert failed.status == "unhealthy"


def test_stable_for_requires_full_true_window() -> None:
    engine = InvariantEngine()
    definition = invariant(TemporalRequirement(operator="stable_for", stable_for_seconds=3))
    history = [(0, world(True)), (2, world(True)), (3, world(True))]
    result = engine.evaluate_all([definition], world(True), 3, history)[0]
    assert result.status == "healthy"


def test_stable_for_includes_state_active_at_window_start() -> None:
    engine = InvariantEngine()
    definition = invariant(TemporalRequirement(operator="stable_for", stable_for_seconds=3))
    # The state was false at t=2 and remained false until the next observation at t=5.
    # At t=6, the interval [3, 5) is therefore still part of the requested window.
    history = [(0, world(True)), (2, world(False)), (5, world(True)), (6, world(True))]
    result = engine.evaluate_all([definition], world(True), 6, history)[0]
    assert result.status == "pending"
