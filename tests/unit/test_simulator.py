from kubeops_core.simulator import SimulationEngine


def test_endpoint_failure_propagates_to_consumer(compiler) -> None:
    scenario = compiler.compile("dependency.endpoint_unreachable.v1")
    run = SimulationEngine().run(scenario)

    assert run.status == "completed"
    final = run.snapshots[-1]
    provider = final.truth_state[scenario.bindings["provider_id"]]
    consumer = final.truth_state[scenario.bindings["consumer_id"]]
    assert provider["observed_state"]["reachable"] is False
    assert consumer["observed_state"]["serviceable"] is False
    assert set(run.final_summary["unhealthy_invariants"]) == {
        "provider.reachable",
        "consumer.serviceable",
    }


def test_partial_observation_produces_unknown_upstream_invariant(compiler) -> None:
    scenario = compiler.compile(
        "dependency.endpoint_unreachable.v1",
        observation_profile_id="consumer_only",
    )
    run = SimulationEngine().run(scenario)
    final = run.snapshots[-1]
    statuses = {item.invariant_id: item.status for item in final.invariant_evaluations}
    assert statuses["provider.reachable"] == "unknown"
    assert statuses["consumer.serviceable"] == "unhealthy"


def test_controller_stall_has_delayed_propagation(compiler) -> None:
    scenario = compiler.compile("controller.convergence_failure.v1")
    run = SimulationEngine().run(scenario)
    event_times = {event.title: event.at_seconds for event in run.timeline}
    assert event_times["Controller stops making progress."] == 2
    propagated = [event for event in run.timeline if event.event_type == "mutation.rule"]
    assert propagated
    assert all(event.at_seconds == 4 for event in propagated)
