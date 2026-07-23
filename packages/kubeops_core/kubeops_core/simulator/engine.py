from __future__ import annotations

import heapq
from copy import deepcopy
from datetime import UTC, datetime
from itertools import count
from typing import Any
from uuid import uuid4

from kubeops_core.invariants.evaluator import InvariantEngine, PredicateEvaluator
from kubeops_core.models.action import ScheduledMutation, StateMutation
from kubeops_core.models.enums import HealthStatus, RunStatus
from kubeops_core.models.run import SimulationRun, TimelineEvent, WorldSnapshot
from kubeops_core.models.scenario import ScenarioInstance

from .observation import ObservationProjector
from .world import MutableWorld


class SimulationEngine:
    """Deterministic, event-driven operational-world simulator."""

    def __init__(self) -> None:
        self._invariants = InvariantEngine()
        self._predicates = PredicateEvaluator()
        self._projector = ObservationProjector()

    def run(self, scenario: ScenarioInstance, *, seed: int = 0) -> SimulationRun:
        started = datetime.now(UTC)
        run_id = f"run-{uuid4().hex[:12]}"
        world = MutableWorld.from_entities(scenario.entities)
        queue: list[tuple[int, int, str, str | None, ScheduledMutation]] = []
        queue_order = count()
        timeline: list[TimelineEvent] = []
        snapshots: list[WorldSnapshot] = []
        observations = []
        world_history: list[tuple[int, dict[str, dict[str, Any]]]] = [(0, world.copy_state())]
        observed_history: list[tuple[int, dict[str, dict[str, Any]]]] = []
        fired_rules: set[str] = set()
        sequence = count()

        for mutation in scenario.disturbance.mutations:
            heapq.heappush(
                queue,
                (mutation.at_seconds, next(queue_order), "disturbance", None, mutation),
            )

        self._append_snapshot(
            scenario,
            world,
            world_history,
            at_seconds=0,
            trigger_event_sequence=None,
            snapshots=snapshots,
            observations=observations,
            observed_history=observed_history,
        )

        status = RunStatus.RUNNING
        try:
            while queue:
                at_seconds, _, source, rule_id, scheduled = heapq.heappop(queue)
                if at_seconds > scenario.max_time_seconds:
                    break
                event_sequence = next(sequence)
                self._apply_mutation(world, scheduled.mutation)
                timeline.append(
                    TimelineEvent(
                        sequence=event_sequence,
                        at_seconds=at_seconds,
                        event_type=f"mutation.{source}",
                        title=scheduled.description,
                        entity_id=scheduled.mutation.entity_id,
                        rule_id=rule_id,
                        mutation_id=scheduled.mutation_id,
                        details=scheduled.mutation.model_dump(mode="json"),
                    )
                )
                world_history.append((at_seconds, world.copy_state()))
                self._append_snapshot(
                    scenario,
                    world,
                    world_history,
                    at_seconds=at_seconds,
                    trigger_event_sequence=event_sequence,
                    snapshots=snapshots,
                    observations=observations,
                    observed_history=observed_history,
                )

                generated = self._schedule_rules(
                    scenario,
                    world.copy_state(),
                    at_seconds,
                    fired_rules,
                    queue_order,
                )
                for item in generated:
                    heapq.heappush(queue, item)
            status = RunStatus.COMPLETED
        except Exception as exc:
            status = RunStatus.FAILED
            timeline.append(
                TimelineEvent(
                    sequence=next(sequence),
                    at_seconds=world_history[-1][0],
                    event_type="simulation.failed",
                    title=str(exc),
                    details={"exception_type": type(exc).__name__},
                )
            )

        final_snapshot = snapshots[-1]
        unhealthy = [
            evaluation.invariant_id
            for evaluation in final_snapshot.invariant_evaluations
            if evaluation.status == HealthStatus.UNHEALTHY
        ]
        unknown = [
            evaluation.invariant_id
            for evaluation in final_snapshot.invariant_evaluations
            if evaluation.status == HealthStatus.UNKNOWN
        ]
        completed = datetime.now(UTC)
        return SimulationRun(
            run_id=run_id,
            scenario_id=scenario.scenario_id,
            family_id=scenario.family_id,
            status=status,
            started_at_iso=started.isoformat(),
            completed_at_iso=completed.isoformat(),
            seed=seed,
            timeline=timeline,
            snapshots=snapshots,
            observations=observations,
            final_summary={
                "simulation_time_seconds": final_snapshot.at_seconds,
                "event_count": len(timeline),
                "snapshot_count": len(snapshots),
                "unhealthy_invariants": unhealthy,
                "unknown_invariants": unknown,
                "healthy_invariant_count": sum(
                    1
                    for evaluation in final_snapshot.invariant_evaluations
                    if evaluation.status == HealthStatus.HEALTHY
                ),
            },
        )

    def _schedule_rules(
        self,
        scenario: ScenarioInstance,
        world_state: dict[str, dict[str, Any]],
        at_seconds: int,
        fired_rules: set[str],
        queue_order: count,
    ) -> list[tuple[int, int, str, str | None, ScheduledMutation]]:
        generated: list[tuple[int, int, str, str | None, ScheduledMutation]] = []
        for rule in scenario.transition_rules:
            if rule.fire_once and rule.rule_id in fired_rules:
                continue
            if rule.conditions and not all(
                self._predicates.evaluate(condition, world_state).satisfied is True
                for condition in rule.conditions
            ):
                continue
            if rule.fire_once:
                fired_rules.add(rule.rule_id)
            for index, effect in enumerate(rule.effects):
                marker = "rule-once" if rule.fire_once else "rule"
                scheduled = ScheduledMutation(
                    mutation_id=f"{marker}:{rule.rule_id}:{at_seconds}:{index}",
                    at_seconds=at_seconds + rule.delay_seconds,
                    description=f"{rule.title}: effect {index + 1}",
                    mutation=effect,
                )
                generated.append(
                    (scheduled.at_seconds, next(queue_order), "rule", rule.rule_id, scheduled)
                )
        return generated

    @staticmethod
    def _apply_mutation(world: MutableWorld, mutation: StateMutation) -> None:
        if mutation.mutation_type == "set_state":
            if not mutation.path:
                raise ValueError("set_state mutation requires path")
            world.set_state(mutation.entity_id, mutation.path, mutation.value)
        elif mutation.mutation_type == "delete_entity":
            world.delete_entity(mutation.entity_id)
        elif mutation.mutation_type == "create_entity":
            if mutation.entity_payload is None:
                raise ValueError("create_entity mutation requires entity_payload")
            world.create_entity(mutation.entity_payload)
        else:
            raise ValueError(f"unsupported mutation type {mutation.mutation_type}")

    def _append_snapshot(
        self,
        scenario: ScenarioInstance,
        world: MutableWorld,
        world_history: list[tuple[int, dict[str, dict[str, Any]]]],
        *,
        at_seconds: int,
        trigger_event_sequence: int | None,
        snapshots: list[WorldSnapshot],
        observations: list[Any],
        observed_history: list[tuple[int, dict[str, dict[str, Any]]]],
    ) -> None:
        truth = world.copy_state()
        observed, emitted = self._projector.project(
            world_history,
            at_seconds,
            scenario.observation_profile,
        )
        observations.extend(emitted)
        observed_history.append((at_seconds, deepcopy(observed)))
        evaluations = self._invariants.evaluate_all(
            scenario.invariants, observed, at_seconds, observed_history
        )
        snapshots.append(
            WorldSnapshot(
                sequence=len(snapshots),
                at_seconds=at_seconds,
                trigger_event_sequence=trigger_event_sequence,
                truth_state=deepcopy(truth),
                observed_state=deepcopy(observed),
                invariant_evaluations=evaluations,
            )
        )
