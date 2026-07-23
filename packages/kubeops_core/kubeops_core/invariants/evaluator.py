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
    FieldsEqual,
    NotPredicate,
    Predicate,
    RelatedCountGte,
)
from kubeops_core.models.relationship import Relationship
from kubeops_core.util import get_path


@dataclass(frozen=True)
class PredicateResult:
    satisfied: bool | None
    actual: Any = None
    expected: Any = None
    explanation: str = ""
    evidence_entity_ids: tuple[str, ...] = ()


class PredicateEvaluator:
    """Evaluate declarative state and graph predicates against a projected world."""

    def evaluate(
        self,
        predicate: Predicate,
        world_state: dict[str, dict[str, Any]],
        relationships: list[Relationship] | None = None,
    ) -> PredicateResult:
        relationships = relationships or []
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
                evidence_entity_ids=(predicate.entity_id,),
            )
        if isinstance(predicate, FieldGte):
            return self._numeric_compare(predicate, world_state, "gte")
        if isinstance(predicate, FieldLte):
            return self._numeric_compare(predicate, world_state, "lte")
        if isinstance(predicate, FieldsEqual):
            return self._fields_equal(predicate, world_state)
        if isinstance(predicate, RelatedCountGte):
            return self._related_count(predicate, world_state, relationships)
        if isinstance(predicate, AllOfPredicate):
            children = [self.evaluate(child, world_state, relationships) for child in predicate.predicates]
            evidence = tuple(dict.fromkeys(entity for child in children for entity in child.evidence_entity_ids))
            if any(child.satisfied is False for child in children):
                return PredicateResult(False, explanation="at least one required predicate is false", evidence_entity_ids=evidence)
            if any(child.satisfied is None for child in children):
                return PredicateResult(None, explanation="at least one required predicate is unknown", evidence_entity_ids=evidence)
            return PredicateResult(True, explanation="all required predicates are true", evidence_entity_ids=evidence)
        if isinstance(predicate, AnyOfPredicate):
            children = [self.evaluate(child, world_state, relationships) for child in predicate.predicates]
            evidence = tuple(dict.fromkeys(entity for child in children for entity in child.evidence_entity_ids))
            if any(child.satisfied is True for child in children):
                return PredicateResult(True, explanation="at least one alternative predicate is true", evidence_entity_ids=evidence)
            if any(child.satisfied is None for child in children):
                return PredicateResult(None, explanation="no alternative is true and at least one is unknown", evidence_entity_ids=evidence)
            return PredicateResult(False, explanation="all alternative predicates are false", evidence_entity_ids=evidence)
        if isinstance(predicate, NotPredicate):
            child = self.evaluate(predicate.predicate, world_state, relationships)
            return PredicateResult(
                None if child.satisfied is None else not child.satisfied,
                actual=child.actual,
                expected=child.expected,
                explanation=f"negation of: {child.explanation}",
                evidence_entity_ids=child.evidence_entity_ids,
            )
        raise TypeError(f"unsupported predicate {type(predicate)!r}")

    def _field_compare(self, predicate: Any, world_state: dict[str, dict[str, Any]], mode: str) -> PredicateResult:
        entity = world_state.get(predicate.entity_id)
        if entity is None:
            return PredicateResult(None, explanation=f"entity {predicate.entity_id} is unobserved")
        sentinel = object()
        actual = get_path(entity, predicate.path, sentinel)
        if actual is sentinel:
            return PredicateResult(None, expected=predicate.value, explanation=f"field {predicate.path} is unobserved", evidence_entity_ids=(predicate.entity_id,))
        satisfied = actual == predicate.value if mode == "equals" else actual != predicate.value
        operator = "==" if mode == "equals" else "!="
        return PredicateResult(
            satisfied,
            actual=actual,
            expected=predicate.value,
            explanation=f"{predicate.entity_id}.{predicate.path} {operator} {predicate.value!r}; actual={actual!r}",
            evidence_entity_ids=(predicate.entity_id,),
        )

    def _numeric_compare(self, predicate: Any, world_state: dict[str, dict[str, Any]], mode: str) -> PredicateResult:
        entity = world_state.get(predicate.entity_id)
        if entity is None:
            return PredicateResult(None, explanation=f"entity {predicate.entity_id} is unobserved")
        sentinel = object()
        actual = get_path(entity, predicate.path, sentinel)
        if actual is sentinel or not isinstance(actual, (int, float)):
            return PredicateResult(None, expected=predicate.value, explanation=f"numeric field {predicate.path} is unavailable", evidence_entity_ids=(predicate.entity_id,))
        satisfied = actual >= predicate.value if mode == "gte" else actual <= predicate.value
        operator = ">=" if mode == "gte" else "<="
        return PredicateResult(
            satisfied,
            actual=actual,
            expected=predicate.value,
            explanation=f"{predicate.entity_id}.{predicate.path} {operator} {predicate.value}; actual={actual}",
            evidence_entity_ids=(predicate.entity_id,),
        )

    def _fields_equal(self, predicate: FieldsEqual, world_state: dict[str, dict[str, Any]]) -> PredicateResult:
        left = world_state.get(predicate.left_entity_id)
        right = world_state.get(predicate.right_entity_id)
        if left is None or right is None:
            return PredicateResult(None, explanation="one or both compared entities are unobserved")
        sentinel = object()
        left_value = get_path(left, predicate.left_path, sentinel)
        right_value = get_path(right, predicate.right_path, sentinel)
        if left_value is sentinel or right_value is sentinel:
            return PredicateResult(None, explanation="one or both compared fields are unavailable", evidence_entity_ids=(predicate.left_entity_id, predicate.right_entity_id))
        return PredicateResult(
            left_value == right_value,
            actual={"left": left_value, "right": right_value},
            expected="equal",
            explanation=f"{predicate.left_entity_id}.{predicate.left_path} == {predicate.right_entity_id}.{predicate.right_path}",
            evidence_entity_ids=(predicate.left_entity_id, predicate.right_entity_id),
        )

    def _related_count(
        self,
        predicate: RelatedCountGte,
        world_state: dict[str, dict[str, Any]],
        relationships: list[Relationship],
    ) -> PredicateResult:
        candidates: list[str] = []
        for relationship in relationships:
            if predicate.relationship_types and relationship.relationship_type not in predicate.relationship_types:
                continue
            target_id: str | None = None
            if predicate.direction in {"outgoing", "either"} and relationship.source_id == predicate.source_entity_id:
                target_id = relationship.target_id
            elif predicate.direction in {"incoming", "either"} and relationship.target_id == predicate.source_entity_id:
                target_id = relationship.source_id
            if target_id is None:
                continue
            if predicate.target_path:
                target = world_state.get(target_id)
                if target is None:
                    continue
                sentinel = object()
                value = get_path(target, predicate.target_path, sentinel)
                if value is sentinel or value != predicate.target_equals:
                    continue
            candidates.append(target_id)
        unique = sorted(set(candidates))
        return PredicateResult(
            len(unique) >= predicate.minimum,
            actual=len(unique),
            expected=predicate.minimum,
            explanation=f"{predicate.source_entity_id} has {len(unique)} matching related entities; minimum={predicate.minimum}",
            evidence_entity_ids=tuple([predicate.source_entity_id, *unique]),
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
        relationships: list[Relationship] | None = None,
    ) -> list[InvariantEvaluation]:
        history = observed_history or [(at_seconds, observed_world)]
        evaluations: list[InvariantEvaluation] = []
        for invariant in invariants:
            result = self._predicates.evaluate(invariant.predicate, observed_world, relationships)
            status, temporal_explanation = self._apply_temporal(
                invariant, result, at_seconds, history, relationships or []
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
                    evidence_entity_ids=list(result.evidence_entity_ids) or [invariant.subject_id],
                )
            )
        return evaluations

    def _apply_temporal(
        self,
        invariant: InvariantDefinition,
        current: PredicateResult,
        at_seconds: int,
        history: list[tuple[int, dict[str, dict[str, Any]]]],
        relationships: list[Relationship],
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
            results = [self._predicates.evaluate(invariant.predicate, state, relationships) for _, state in relevant]
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
