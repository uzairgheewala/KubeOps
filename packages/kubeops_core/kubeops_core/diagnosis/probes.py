from __future__ import annotations

from collections import defaultdict
from uuid import uuid4

from kubeops_core.models.diagnosis import EvidenceFact, Hypothesis, ProbeIntent, ProbePlan
from kubeops_core.util import utc_now_iso

from .catalog import DiagnosticCatalog
from .engine import fact_type_matches


_COST = {"negligible": 0.25, "low": 1.0, "medium": 3.0, "high": 8.0}


class ProbePlanner:
    """Ranks read-only probes by expected hypothesis discrimination per unit cost."""

    def __init__(self, catalog: DiagnosticCatalog) -> None:
        self._catalog = catalog

    def plan(
        self,
        incident_id: str,
        hypotheses: list[Hypothesis],
        evidence: list[EvidenceFact],
        *,
        evidence_budget: int | None = 5,
    ) -> ProbePlan:
        unresolved = [
            item for item in hypotheses
            if item.status in {"candidate", "supported", "unresolved"} and not item.metadata.get("generic")
        ]
        if not unresolved:
            return ProbePlan(
                plan_id=f"probe-plan-{uuid4().hex[:12]}",
                incident_id=incident_id,
                created_at_iso=utc_now_iso(),
                probes=[],
                stopping_reason="No unresolved specialized hypotheses remain.",
                evidence_budget=evidence_budget,
            )

        intent_hypotheses: dict[str, list[Hypothesis]] = defaultdict(list)
        for hypothesis in unresolved:
            for intent_id in hypothesis.required_probe_ids:
                intent_hypotheses[intent_id].append(hypothesis)

        probes: list[ProbeIntent] = []
        existing_types = {item.fact_type for item in evidence}
        for intent_id, affected in intent_hypotheses.items():
            try:
                intent = self._catalog.intent(intent_id)
            except KeyError:
                continue
            predicted = sorted({fact for item in affected for fact in item.predictions})
            required_types = list(dict.fromkeys([*intent.required_fact_types, *predicted]))
            missing = [
                fact_type for fact_type in required_types
                if not any(fact_type_matches(fact_type, item) for item in existing_types)
            ]
            if not missing:
                continue
            candidates = [
                item for item in self._catalog.collectors()
                if (
                    item.collector_id in intent.preferred_collector_ids
                    or set(item.questions_answered) & set(intent.questions_answered)
                )
                and any(
                    fact_type_matches(required, provided)
                    for required in missing
                    for provided in item.fact_types
                )
            ]
            if not candidates:
                continue
            cheapest = min(_COST[item.cost_class] for item in candidates)
            family_diversity = len({item.family_id for item in affected})
            information_gain = len(affected) + family_diversity * 0.5 + len(missing) * 0.25
            score = information_gain / max(cheapest, 0.25)
            subjects = sorted({subject for item in affected for subject in item.subject_ids})
            support_outcomes = sorted({prediction for item in affected for prediction in item.predictions})
            probes.append(
                ProbeIntent(
                    probe_id=f"probe-{uuid4().hex[:12]}",
                    title=intent.title or intent.question,
                    evidence_intent_id=intent_id,
                    applicable_hypothesis_ids=[item.hypothesis_id for item in affected],
                    discriminates_hypothesis_ids=[item.hypothesis_id for item in affected],
                    candidate_collector_ids=[item.collector_id for item in sorted(candidates, key=lambda item: (_COST[item.cost_class], item.collector_id))],
                    expected_outcomes={
                        "support": support_outcomes or missing,
                        "contradict": sorted({fact for item in affected for fact in item.metadata.get("contradicting_fact_types", [])}),
                    },
                    rationale=(
                        f"Collects {', '.join(missing)} to discriminate {len(affected)} unresolved "
                        f"hypotheses across {family_diversity} causal families."
                    ),
                    information_gain_score=round(score, 4),
                    cost_score=cheapest,
                    risk_class=intent.risk_class,
                    metadata={"subject_ids": subjects, "missing_fact_types": missing},
                )
            )
        probes.sort(key=lambda item: (-item.information_gain_score, item.cost_score, item.probe_id))
        if evidence_budget is not None:
            probes = probes[:evidence_budget]
        return ProbePlan(
            plan_id=f"probe-plan-{uuid4().hex[:12]}",
            incident_id=incident_id,
            created_at_iso=utc_now_iso(),
            probes=probes,
            stopping_reason=None if probes else "No applicable read-only collector can resolve the remaining evidence gaps.",
            evidence_budget=evidence_budget,
            metadata={"unresolved_hypothesis_count": len(unresolved)},
        )
