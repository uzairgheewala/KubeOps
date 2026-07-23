from __future__ import annotations

from kubeops_core.invariants.evaluator import InvariantEngine
from kubeops_core.models.enums import HealthStatus
from kubeops_core.models.invariant import InvariantDefinition
from kubeops_core.models.relationship import Relationship
from kubeops_core.models.verification import VerificationCondition, VerificationResult


class VerificationEngine:
    def evaluate(
        self,
        conditions: list[VerificationCondition],
        world_state: dict[str, dict],
        relationships: list[Relationship] | None = None,
        *,
        at_seconds: int = 0,
        history: list[tuple[int, dict[str, dict]]] | None = None,
    ) -> list[VerificationResult]:
        invariants = [
            InvariantDefinition(
                invariant_id=condition.condition_id,
                title=condition.title,
                family="recoverability",
                subject_id=self._subject(condition),
                predicate=condition.predicate,
                temporal=condition.temporal,
                severity="critical" if condition.required else "warning",
            )
            for condition in conditions
        ]
        evaluations = InvariantEngine().evaluate_all(
            invariants,
            world_state,
            at_seconds,
            observed_history=history,
            relationships=relationships or [],
        )
        return [
            VerificationResult(
                result_id=f"verification:{evaluation.invariant_id}:{at_seconds}",
                condition_id=evaluation.invariant_id,
                status=evaluation.status,
                evaluated_at_seconds=at_seconds,
                explanation=evaluation.explanation,
                evidence_ids=evaluation.evidence_entity_ids,
                actual_value=evaluation.actual_value,
            )
            for evaluation in evaluations
        ]

    @staticmethod
    def successful(conditions: list[VerificationCondition], results: list[VerificationResult]) -> bool:
        required = {item.condition_id for item in conditions if item.required}
        statuses = {item.condition_id: item.status for item in results}
        return all(statuses.get(condition_id) == HealthStatus.HEALTHY for condition_id in required)

    @staticmethod
    def protected_violation(conditions: list[VerificationCondition], results: list[VerificationResult]) -> bool:
        protected = {
            item.condition_id
            for item in conditions
            if item.level == "side_effect_guard"
        }
        statuses = {item.condition_id: item.status for item in results}
        return any(statuses.get(condition_id) == HealthStatus.UNHEALTHY for condition_id in protected)

    @staticmethod
    def _subject(condition: VerificationCondition) -> str:
        predicate = condition.predicate
        for attribute in ("entity_id", "source_entity_id", "left_entity_id"):
            value = getattr(predicate, attribute, None)
            if value:
                return str(value)
        return "environment"
