from kubeops_core.models.composition import CompositionComponent, ScenarioComposition
from kubeops_core.scenarios import ScenarioComposer
from kubeops_core.simulator import SimulationEngine


def test_concurrent_composition_namespaces_components(compiler) -> None:
    spec = ScenarioComposition(
        composition_id="dual-failure",
        title="Concurrent network and controller failure",
        operator="concurrent",
        components=[
            CompositionComponent(
                alias="network",
                family_id="dependency.endpoint_unreachable.v1",
            ),
            CompositionComponent(
                alias="controller",
                family_id="controller.convergence_failure.v1",
            ),
        ],
    )
    scenario = ScenarioComposer(compiler).compose(spec)
    ids = {entity.entity_id for entity in scenario.entities}
    assert "network::consumer" in ids
    assert "controller::controller" in ids
    assert len(ids) == len(scenario.entities)

    run = SimulationEngine().run(scenario)
    assert "network::provider.reachable" in run.final_summary["unhealthy_invariants"]
    assert "controller::controller.progressing" in run.final_summary["unhealthy_invariants"]


def test_sequential_composition_offsets_second_disturbance(compiler) -> None:
    spec = ScenarioComposition(
        composition_id="ordered-failures",
        title="Sequential failures",
        operator="sequential",
        components=[
            CompositionComponent(
                alias="first",
                family_id="entity.required_absent.v1",
                duration_hint_seconds=5,
            ),
            CompositionComponent(
                alias="second",
                family_id="dependency.authentication_failure.v1",
                duration_hint_seconds=5,
            ),
        ],
        gap_seconds=2,
    )
    scenario = ScenarioComposer(compiler).compose(spec)
    times = [mutation.at_seconds for mutation in scenario.disturbance.mutations]
    assert min(times) == 2
    assert max(times) >= 9


def test_masking_composition_hides_declared_component(compiler) -> None:
    spec = ScenarioComposition(
        composition_id="masked",
        title="Masked upstream failure",
        operator="masking",
        components=[
            CompositionComponent(alias="hidden", family_id="entity.required_absent.v1"),
            CompositionComponent(alias="visible", family_id="dependency.endpoint_unreachable.v1"),
        ],
        masked_aliases={"hidden"},
    )
    scenario = ScenarioComposer(compiler).compose(spec)
    assert all(
        entity_id.startswith("hidden::")
        for entity_id in scenario.observation_profile.hidden_entity_ids
    )
    run = SimulationEngine().run(scenario)
    statuses = {
        item.invariant_id: item.status
        for item in run.snapshots[-1].invariant_evaluations
    }
    assert statuses["hidden::required.exists"] == "unknown"
    assert statuses["visible::provider.reachable"] == "unhealthy"


def test_conditional_composition_activates_from_cross_component_predicate(compiler) -> None:
    from kubeops_core.models.predicate import FieldEquals

    spec = ScenarioComposition(
        composition_id="conditional-auth",
        title="Authentication fails after required resource disappears",
        operator="conditional",
        components=[
            CompositionComponent(
                alias="first",
                family_id="entity.required_absent.v1",
            ),
            CompositionComponent(
                alias="second",
                family_id="dependency.authentication_failure.v1",
                activation_predicate=FieldEquals(
                    entity_id="first::required-resource",
                    path="observed_state.exists",
                    value=False,
                ),
            ),
        ],
    )
    scenario = ScenarioComposer(compiler).compose(spec)
    assert scenario.disturbance.temporal_form == "delayed_effect"
    run = SimulationEngine().run(scenario)
    events = {(event.at_seconds, event.rule_id) for event in run.timeline}
    assert any(rule_id and "second::activation" in rule_id for _, rule_id in events)
    assert "second::dependency.authenticated" in run.final_summary["unhealthy_invariants"]


def test_recovery_interference_is_recovery_induced_and_ordered(compiler) -> None:
    spec = ScenarioComposition(
        composition_id="recovery-interference",
        title="Recovery action exposes a second failure",
        operator="recovery_interference",
        components=[
            CompositionComponent(
                alias="recovery",
                family_id="entity.required_absent.v1",
                duration_hint_seconds=4,
            ),
            CompositionComponent(
                alias="secondary",
                family_id="controller.convergence_failure.v1",
                duration_hint_seconds=4,
            ),
        ],
        gap_seconds=1,
    )
    scenario = ScenarioComposer(compiler).compose(spec)
    assert scenario.disturbance.temporal_form == "recovery_induced"
    first_times = [
        mutation.at_seconds
        for mutation in scenario.disturbance.mutations
        if mutation.mutation_id.startswith("recovery::")
    ]
    second_times = [
        mutation.at_seconds
        for mutation in scenario.disturbance.mutations
        if mutation.mutation_id.startswith("secondary::")
    ]
    assert max(first_times) < min(second_times)
