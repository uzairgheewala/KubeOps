from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kubeops_core.models.enums import HealthStatus
from kubeops_core.models.invariant import InvariantDefinition, InvariantEvaluation
from kubeops_core.models.predicate import (
    AllOfPredicate,
    AnyOfPredicate,
    FieldEquals,
    FieldExists,
    FieldGte,
    FieldLte,
    FieldNotEquals,
    NotPredicate,
    Predicate,
)
from kubeops_core.util import get_path


@dataclass(frozen=True)
class PredicateResult:
    satisfied: bool | None
    actual: Any = None
    expected: Any = None
    explanation: str = ""


class PredicateEvaluator:
    """Evaluate the declarative predicate subset used by Release 0.1."""

    def evaluate(
        self,
        predicate: Predicate,
        world_state: dict[str, dict[str, Any]],
    ) -> PredicateResult:
        if isinstance(predicate, FieldEquals):
            return self._field_compare(predicate, world_state, "equals")
        if isinstance(predicate, FieldNotEquals):
            return self._field_compare(predicate, world_state, "not_equals")
        if isinstance(predicate, FieldExists):
            entity = world_state.get(predicate.entity_id)
            if entity is None:
                return PredicateResult(None, explanation=f"entity {predicate.entity_id} is unobserved")
            sentinel = object()
            actual = get_path(entity, predicate.path, sentinel)
            exists = actual is not sentinel
            return PredicateResult(
                exists == predicate.expected,
                actual=exists,
                expected=predicate.expected,
                explanation=f"{predicate.entity_id}.{predicate.path} existence is {exists}",
            )
        if isinstance(predicate, FieldGte):
            return self._numeric_compare(predicate, world_state, "gte")
        if isinstance(predicate, FieldLte):
            return self._numeric_compare(predicate, world_state, "lte")
        if isinstance(predicate, AllOfPredicate):
            children = [self.evaluate(child, world_state) for child in predicate.predicates]
            if any(child.satisfied is False for child in children):
                return PredicateResult(False, explanation="at least one required predicate is false")
            if any(child.satisfied is None for child in children):
                return PredicateResult(None, explanation="at least one required predicate is unknown")
            return PredicateResult(True, explanation="all required predicates are true")
        if isinstance(predicate, AnyOfPredicate):
            children = [self.evaluate(child, world_state) for child in predicate.predicates]
            if any(child.satisfied is True for child in children):
                return PredicateResult(True, explanation="at least one alternative predicate is true")
            if any(child.satisfied is None for child in children):
                return PredicateResult(None, explanation="no alternative is true and at least one is unknown")
            return PredicateResult(False, explanation="all alternative predicates are false")
        if isinstance(predicate, NotPredicate):
            child = self.evaluate(predicate.predicate, world_state)
            return PredicateResult(
                None if child.satisfied is None else not child.satisfied,
                actual=child.actual,
                expected=child.expected,
                explanation=f"negation of: {child.explanation}",
            )
        raise TypeError(f"unsupported predicate {type(predicate)!r}")

    def _field_compare(self, predicate: Any, world_state: dict[str, dict[str, Any]], mode: str) -> PredicateResult:
        entity = world_state.get(predicate.entity_id)
        if entity is None:
            return PredicateResult(None, explanation=f"entity {predicate.entity_id} is unobserved")
        sentinel = object()
        actual = get_path(entity, predicate.path, sentinel)
        if actual is sentinel:
            return PredicateResult(None, expected=predicate.value, explanation=f"field {predicate.path} is unobserved")
        satisfied = actual == predicate.value if mode == "equals" else actual != predicate.value
        operator = "==" if mode == "equals" else "!="
        return PredicateResult(
            satisfied,
            actual=actual,
            expected=predicate.value,
            explanation=f"{predicate.entity_id}.{predicate.path} {operator} {predicate.value!r}; actual={actual!r}",
        )

    def _numeric_compare(self, predicate: Any, world_state: dict[str, dict[str, Any]], mode: str) -> PredicateResult:
        entity = world_state.get(predicate.entity_id)
        if entity is None:
            return PredicateResult(None, explanation=f"entity {predicate.entity_id} is unobserved")
        sentinel = object()
        actual = get_path(entity, predicate.path, sentinel)
        if actual is sentinel or not isinstance(actual, (int, float)):
            return PredicateResult(None, expected=predicate.value, explanation=f"numeric field {predicate.path} is unavailable")
        satisfied = actual >= predicate.value if mode == "gte" else actual <= predicate.value
        operator = ">=" if mode == "gte" else "<="
        return PredicateResult(
            satisfied,
            actual=actual,
            expected=predicate.value,
            explanation=f"{predicate.entity_id}.{predicate.path} {operator} {predicate.value}; actual={actual}",
        )


class InvariantEngine:
    def __init__(self) -> None:
        self._predicates = PredicateEvaluator()

    def evaluate_all(
        self,
        invariants: list[InvariantDefinition],
        observed_world: dict[str, dict[str, Any]],
        at_seconds: int,
        observed_history: list[tuple[int, dict[str, dict[str, Any]]]] | None = None,
    ) -> list[InvariantEvaluation]:
        history = observed_history or [(at_seconds, observed_world)]
        evaluations: list[InvariantEvaluation] = []
        for invariant in invariants:
            result = self._predicates.evaluate(invariant.predicate, observed_world)
            status, temporal_explanation = self._apply_temporal(
                invariant, result, at_seconds, history
            )
            explanation = result.explanation
            if temporal_explanation:
                explanation = f"{explanation}; {temporal_explanation}"
            evaluations.append(
                InvariantEvaluation(
                    invariant_id=invariant.invariant_id,
                    status=status,
                    evaluated_at=at_seconds,
                    actual_value=result.actual,
                    expected=result.expected,
                    explanation=explanation,
                    evidence_entity_ids=[invariant.subject_id],
                )
            )
        return evaluations

    def _apply_temporal(
        self,
        invariant: InvariantDefinition,
        current: PredicateResult,
        at_seconds: int,
        history: list[tuple[int, dict[str, dict[str, Any]]]],
    ) -> tuple[HealthStatus, str]:
        temporal = invariant.temporal
        if temporal.operator == "immediate":
            return self._status(current.satisfied), ""

        if temporal.operator == "eventually":
            if current.satisfied is True:
                return HealthStatus.HEALTHY, "bounded eventuality has been satisfied"
            deadline = temporal.within_seconds
            if deadline is None:
                return HealthStatus.PENDING, "waiting for eventual satisfaction without a deadline"
            if at_seconds < deadline:
                return HealthStatus.PENDING, f"waiting until the {deadline}s deadline"
            if current.satisfied is None:
                return HealthStatus.UNKNOWN, f"deadline {deadline}s reached without sufficient evidence"
            return HealthStatus.UNHEALTHY, f"deadline {deadline}s elapsed before satisfaction"

        if temporal.operator == "stable_for":
            if current.satisfied is False:
                return HealthStatus.UNHEALTHY, "current state violates the stability predicate"
            if current.satisfied is None:
                return HealthStatus.UNKNOWN, "current stability state is unobservable"
            required = temporal.stable_for_seconds or 0
            window_start = at_seconds - required
            baseline: tuple[int, dict[str, dict[str, Any]]] | None = None
            changes: list[tuple[int, dict[str, dict[str, Any]]]] = []
            for time, state in history:
                if time <= window_start:
                    baseline = (time, state)
                elif time <= at_seconds:
                    changes.append((time, state))
            if baseline is None:
                return HealthStatus.PENDING, f"less than {required}s of observation history is available"
            relevant = [baseline, *changes]
            results = [self._predicates.evaluate(invariant.predicate, state) for _, state in relevant]
            if any(result.satisfied is None for result in results):
                return HealthStatus.UNKNOWN, "the stability window contains unknown observations"
            if any(result.satisfied is False for result in results):
                return HealthStatus.PENDING, f"predicate has not remained true for {required}s"
            return HealthStatus.HEALTHY, f"predicate remained true for at least {required}s"

        raise ValueError(f"unsupported temporal operator {temporal.operator}")

    @staticmethod
    def _status(satisfied: bool | None) -> HealthStatus:
        if satisfied is True:
            return HealthStatus.HEALTHY
        if satisfied is False:
            return HealthStatus.UNHEALTHY
        return HealthStatus.UNKNOWN
