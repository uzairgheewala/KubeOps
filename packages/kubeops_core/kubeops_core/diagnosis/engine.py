from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Iterable
from uuid import uuid4

from kubeops_core.models.diagnosis import (
    CausalEdge,
    DiagnosisCertificate,
    EvidenceFact,
    Hypothesis,
    Symptom,
)
from kubeops_core.models.enums import HealthStatus, InvariantFamily
from kubeops_core.models.health import CompiledOperationalProfile, OperationalProfileAssessment
from kubeops_core.models.invariant import InvariantDefinition, InvariantEvaluation
from kubeops_core.models.topology import TopologyGraph
from kubeops_core.util import utc_now_iso

from .catalog import DiagnosticCatalog


def fact_type_matches(pattern: str, fact_type: str) -> bool:
    if pattern == fact_type:
        return True
    if pattern.endswith(".*"):
        return fact_type.startswith(pattern[:-1])
    return fact_type.startswith(f"{pattern}.") or pattern.startswith(f"{fact_type}.")


class SymptomDeriver:
    def derive(
        self,
        compiled: CompiledOperationalProfile,
        assessment: OperationalProfileAssessment,
        evidence: list[EvidenceFact],
    ) -> tuple[list[Symptom], list[EvidenceFact]]:
        definitions = {item.invariant_id: item for item in compiled.invariants}
        existing = {item.evidence_id: item for item in evidence}
        symptoms: list[Symptom] = []
        for evaluation in assessment.evaluations:
            if evaluation.status == HealthStatus.HEALTHY:
                continue
            definition = definitions.get(evaluation.invariant_id)
            if definition is None:
                continue
            facts = self._facts_for_evaluation(definition, evaluation, assessment)
            for fact in facts:
                existing.setdefault(fact.evidence_id, fact)
            role = "initial" if evaluation.invariant_id in assessment.violated_invariant_ids else "unknown"
            symptoms.append(
                Symptom(
                    symptom_id=f"symptom-{hashlib.sha256(evaluation.invariant_id.encode()).hexdigest()[:16]}",
                    symptom_type=f"invariant.{definition.family}.{'violated' if evaluation.status == HealthStatus.UNHEALTHY else str(evaluation.status)}",
                    statement=evaluation.explanation,
                    subject_ids=list(dict.fromkeys([definition.subject_id, *evaluation.evidence_entity_ids])),
                    invariant_id=definition.invariant_id,
                    invariant_family=definition.family,
                    health_status=evaluation.status,
                    causal_role=role,
                    confidence=1.0 if evaluation.status == HealthStatus.UNHEALTHY else 0.65,
                    evidence_ids=[item.evidence_id for item in facts],
                    first_observed_at_seconds=evaluation.evaluated_at,
                    metadata={"title": definition.title, "severity": str(definition.severity)},
                )
            )
        return symptoms, sorted(existing.values(), key=lambda item: item.evidence_id)

    def _facts_for_evaluation(
        self,
        definition: InvariantDefinition,
        evaluation: InvariantEvaluation,
        assessment: OperationalProfileAssessment,
    ) -> list[EvidenceFact]:
        status = str(evaluation.status)
        token = f"{assessment.assessment_id}:{definition.invariant_id}:{status}:{evaluation.actual_value}"
        base_id = hashlib.sha256(token.encode()).hexdigest()[:18]
        common = dict(
            subject_ids=[definition.subject_id, *[item for item in evaluation.evidence_entity_ids if item != definition.subject_id]],
            collector_id="health.invariant_evaluation.v1",
            observed_at_iso=assessment.evaluated_at_iso,
            authority="authoritative",
            freshness_seconds=0,
            attributes={
                "invariant_id": definition.invariant_id,
                "invariant_family": str(definition.family),
                "health_status": status,
                "expected": evaluation.expected,
            },
        )
        facts = [
            EvidenceFact(
                evidence_id=f"ev-{base_id}-invariant",
                fact_type="invariant.violated" if evaluation.status == HealthStatus.UNHEALTHY else f"invariant.{status}",
                statement=evaluation.explanation,
                value=evaluation.actual_value,
                **common,
            ),
            EvidenceFact(
                evidence_id=f"ev-{base_id}-family",
                fact_type=f"invariant.{definition.family}.{status}",
                statement=evaluation.explanation,
                value=evaluation.actual_value,
                **common,
            ),
        ]
        if evaluation.status != HealthStatus.UNHEALTHY:
            return facts
        mapped = _family_violation_fact(definition.family, evaluation.actual_value)
        if mapped:
            fact_type, statement, value = mapped
            facts.append(
                EvidenceFact(
                    evidence_id=f"ev-{base_id}-semantic",
                    fact_type=fact_type,
                    statement=f"{definition.subject_id}: {statement}",
                    value=value,
                    **common,
                )
            )
        return facts


class HypothesisEngine:
    def __init__(self, catalog: DiagnosticCatalog) -> None:
        self._catalog = catalog

    def generate(
        self,
        symptoms: list[Symptom],
        evidence: list[EvidenceFact],
        topology: TopologyGraph,
    ) -> tuple[list[Hypothesis], list[CausalEdge]]:
        hypotheses: list[Hypothesis] = []
        edges: list[CausalEdge] = []
        by_id: dict[str, Hypothesis] = {}
        generic_template = self._catalog.template("operational.invariant_violation.v1")
        entity_types = {item.entity_id: {item.entity_type, *item.entity_type_lineage} for item in topology.entities}

        for symptom in symptoms:
            if symptom.invariant_family is None:
                templates = [generic_template]
            else:
                templates = self._catalog.templates_for_family(symptom.invariant_family)
                if generic_template not in templates:
                    templates.insert(0, generic_template)
            parent_hypothesis_id: str | None = None
            for template in sorted(templates, key=lambda item: (item.specificity, item.template_id)):
                if template.symptom_types and symptom.symptom_type not in template.symptom_types:
                    continue
                supported_types = set(template.metadata.get("supported_entity_types", []))
                if supported_types and not any(entity_types.get(subject_id, set()) & supported_types for subject_id in symptom.subject_ids):
                    continue
                subject = symptom.subject_ids[0] if symptom.subject_ids else "unknown subject"
                hypothesis_id = f"hyp-{hashlib.sha256(f'{symptom.symptom_id}:{template.template_id}'.encode()).hexdigest()[:18]}"
                related_evidence = [item for item in evidence if _subjects_overlap(item.subject_ids, symptom.subject_ids)]
                supporting = [
                    item for item in related_evidence
                    if any(fact_type_matches(pattern, item.fact_type) for pattern in template.supporting_fact_types)
                ]
                contradicting = [
                    item for item in related_evidence
                    if any(fact_type_matches(pattern, item.fact_type) for pattern in template.contradicting_fact_types)
                ]
                missing_predictions = [
                    prediction for prediction in sorted(template.predicted_fact_types)
                    if not any(fact_type_matches(prediction, item.fact_type) for item in related_evidence)
                ]
                status, confidence, components = self._score(template.generic, template.specificity, supporting, contradicting, missing_predictions)
                parent = None if template.generic else parent_hypothesis_id
                hypothesis = Hypothesis(
                    hypothesis_id=hypothesis_id,
                    family_id=template.family_id,
                    template_id=template.template_id,
                    parent_hypothesis_id=parent,
                    claim=template.claim_template.format(subject=subject, family=symptom.invariant_family or "unknown"),
                    subject_ids=symptom.subject_ids,
                    status=status,
                    confidence=confidence,
                    explains_symptom_ids=[symptom.symptom_id],
                    supporting_evidence_ids=[item.evidence_id for item in supporting],
                    contradicting_evidence_ids=[item.evidence_id for item in contradicting],
                    required_probe_ids=list(template.evidence_intent_ids) if missing_predictions and status not in {"ruled_out", "contradicted"} else [],
                    predictions=missing_predictions,
                    score_components=components,
                    metadata={"title": template.title, "generic": template.generic, "specificity": template.specificity},
                )
                if hypothesis_id not in by_id:
                    hypotheses.append(hypothesis)
                    by_id[hypothesis_id] = hypothesis
                if template.generic:
                    parent_hypothesis_id = hypothesis_id
                edges.append(
                    CausalEdge(
                        edge_id=f"edge-{uuid4().hex[:12]}",
                        source_id=hypothesis_id,
                        target_id=symptom.symptom_id,
                        relation="explains",
                        statement=f"{template.title} explains {symptom.statement}",
                        confidence=confidence,
                        evidence_ids=[item.evidence_id for item in supporting],
                    )
                )
                for item in supporting:
                    edges.append(
                        CausalEdge(
                            edge_id=f"edge-{uuid4().hex[:12]}",
                            source_id=item.evidence_id,
                            target_id=hypothesis_id,
                            relation="supports",
                            statement=item.statement,
                            confidence=_authority_confidence(item.authority),
                            evidence_ids=[item.evidence_id],
                        )
                    )
                for item in contradicting:
                    edges.append(
                        CausalEdge(
                            edge_id=f"edge-{uuid4().hex[:12]}",
                            source_id=item.evidence_id,
                            target_id=hypothesis_id,
                            relation="contradicts",
                            statement=item.statement,
                            confidence=_authority_confidence(item.authority),
                            evidence_ids=[item.evidence_id],
                        )
                    )

        edges.extend(self._propagation_edges(symptoms, topology))
        hypotheses = self._mark_unexplained(hypotheses, symptoms)
        return sorted(hypotheses, key=lambda item: (-item.confidence, item.family_id, item.hypothesis_id)), edges

    @staticmethod
    def _score(
        generic: bool,
        specificity: int,
        supporting: list[EvidenceFact],
        contradicting: list[EvidenceFact],
        missing_predictions: list[str],
    ) -> tuple[str, float, dict[str, float]]:
        support_score = sum(_authority_confidence(item.authority) for item in supporting)
        contradiction_score = sum(_authority_confidence(item.authority) for item in contradicting)
        specificity_score = min(specificity * 0.04, 0.2)
        missing_penalty = min(len(missing_predictions) * 0.08, 0.32)
        base = 0.22 if generic else 0.15
        confidence = max(0.01, min(0.99, base + support_score * 0.32 + specificity_score - contradiction_score * 0.42 - missing_penalty))
        if contradiction_score >= support_score and contradiction_score > 0:
            status = "ruled_out" if support_score == 0 else "contradicted"
        elif supporting and not missing_predictions and support_score >= 0.8:
            status = "proven"
        elif supporting:
            status = "supported"
        else:
            status = "candidate"
        return status, round(confidence, 4), {
            "base": base,
            "support": round(support_score, 4),
            "contradiction": round(contradiction_score, 4),
            "specificity": round(specificity_score, 4),
            "missing_prediction_penalty": round(missing_penalty, 4),
        }

    @staticmethod
    def _propagation_edges(symptoms: list[Symptom], topology: TopologyGraph) -> list[CausalEdge]:
        symptom_by_subject: dict[str, list[Symptom]] = defaultdict(list)
        for symptom in symptoms:
            for subject in symptom.subject_ids:
                symptom_by_subject[subject].append(symptom)
        edges: list[CausalEdge] = []
        dependency_types = {
            "requires_for_readiness", "requires_for_service", "requires_for_liveness",
            "routes_to", "selects", "connects_to", "depends_on", "owned_by",
        }
        for relationship in topology.relationships:
            if relationship.relationship_type not in dependency_types:
                continue
            source_symptoms = symptom_by_subject.get(relationship.source_id, [])
            target_symptoms = symptom_by_subject.get(relationship.target_id, [])
            for target in target_symptoms:
                for source in source_symptoms:
                    if source.symptom_id == target.symptom_id:
                        continue
                    edges.append(
                        CausalEdge(
                            edge_id=f"edge-{uuid4().hex[:12]}",
                            source_id=target.symptom_id,
                            target_id=source.symptom_id,
                            relation="propagates_to",
                            statement=(
                                f"Violation at {relationship.target_id} may propagate to {relationship.source_id} "
                                f"through {relationship.relationship_type}."
                            ),
                            confidence=relationship.confidence * 0.75,
                            evidence_ids=[],
                        )
                    )
        return edges

    @staticmethod
    def _mark_unexplained(hypotheses: list[Hypothesis], symptoms: list[Symptom]) -> list[Hypothesis]:
        all_symptoms = {item.symptom_id for item in symptoms}
        result: list[Hypothesis] = []
        for item in hypotheses:
            result.append(item.model_copy(update={"unexplained_symptom_ids": sorted(all_symptoms - set(item.explains_symptom_ids))}))
        return result


class DiagnosisCertificateBuilder:
    def build(
        self,
        incident_id: str,
        violated_invariant_ids: list[str],
        hypotheses: list[Hypothesis],
        evidence: list[EvidenceFact],
        edges: list[CausalEdge],
    ) -> DiagnosisCertificate:
        non_generic = [item for item in hypotheses if not item.metadata.get("generic") and item.status not in {"ruled_out", "contradicted"}]
        proven = [item for item in non_generic if item.status == "proven"]
        supported = [item for item in non_generic if item.status == "supported"]
        candidates = [item for item in non_generic if item.status in {"candidate", "unresolved"}]
        ruled_out = [item for item in hypotheses if item.status in {"ruled_out", "contradicted"}]
        generic = [item for item in hypotheses if item.metadata.get("generic") and item.status not in {"ruled_out", "contradicted"}]

        root_ids: list[str] = []
        if proven:
            root_ids = [item.hypothesis_id for item in _minimal_roots(proven)]
            status = "root_cause_identified" if len(root_ids) == 1 else "multiple_plausible_causes"
        elif supported:
            root_ids = [item.hypothesis_id for item in _minimal_roots(supported)]
            status = "failure_class_identified" if len(root_ids) == 1 else "multiple_plausible_causes"
        elif candidates:
            status = "insufficient_evidence"
        elif generic:
            root_ids = [generic[0].hypothesis_id]
            status = "partial_causal_chain"
        else:
            status = "unknown_semantics"

        selected = [item for item in hypotheses if item.hypothesis_id in root_ids]
        confidence = round(sum(item.confidence for item in selected) / len(selected), 4) if selected else 0.0
        unresolved = [item.hypothesis_id for item in candidates]
        questions = sorted({probe for item in [*supported, *candidates] for probe in item.required_probe_ids})
        nearest = sorted({item.family_id for item in [*selected, *generic]})
        causal_chain = [edge.statement for edge in edges if edge.relation in {"propagates_to", "explains"}][:50]
        return DiagnosisCertificate(
            certificate_id=f"diag-cert-{uuid4().hex[:12]}",
            incident_id=incident_id,
            issued_at_iso=utc_now_iso(),
            violated_invariant_ids=violated_invariant_ids,
            causal_chain=causal_chain,
            causal_edges=edges,
            root_cause_hypothesis_ids=root_ids,
            ruled_out_hypothesis_ids=[item.hypothesis_id for item in ruled_out],
            unresolved_hypothesis_ids=unresolved,
            unresolved_questions=questions,
            evidence_ids=[item.evidence_id for item in evidence],
            status=status,  # type: ignore[arg-type]
            confidence=confidence,
            nearest_supported_family_ids=nearest,
            metadata={
                "hypothesis_count": len(hypotheses),
                "proven_count": len(proven),
                "supported_count": len(supported),
                "candidate_count": len(candidates),
            },
        )


def _family_violation_fact(family: InvariantFamily | str, actual: object) -> tuple[str, str, object] | None:
    family = InvariantFamily(str(family))
    mapping = {
        InvariantFamily.EXISTENCE: ("entity.exists.false", "required entity does not exist", False),
        InvariantFamily.REACHABILITY: ("endpoint.reachable.false", "required endpoint is unreachable", False),
        InvariantFamily.AUTHENTICATION: ("authentication.state.failed", "authentication contract failed", actual),
        InvariantFamily.AUTHORIZATION: ("authorization.denied", "authorization contract was denied", actual),
        InvariantFamily.PLACEMENT: ("placement.unsatisfied_constraint", "placement constraints are unsatisfied", actual),
        InvariantFamily.LIFECYCLE_PROGRESS: ("controller.progress.false", "controller is not converging", actual),
        InvariantFamily.READINESS: ("entity.ready.false", "component is not ready", False),
        InvariantFamily.LIVENESS: ("entity.serviceable.false", "component is not live or serviceable", False),
        InvariantFamily.CAPACITY: ("capacity.exhausted", "required capacity is exhausted", actual),
        InvariantFamily.CONSISTENCY: ("state.divergence", "state representations diverge", actual),
        InvariantFamily.FRESHNESS: ("state.stale", "required state is stale", actual),
        InvariantFamily.OBSERVABILITY: ("observability.gap", "required evidence is unavailable", actual),
        InvariantFamily.CONFIGURATION: ("configuration.reference_invalid", "configuration contract is invalid", actual),
        InvariantFamily.STRUCTURAL: ("configuration.reference_invalid", "structural relationship is invalid", actual),
        InvariantFamily.IDENTITY_RESOLUTION: ("configuration.reference_invalid", "identity or reference resolution failed", actual),
    }
    return mapping.get(family)


def _subjects_overlap(left: Iterable[str], right: Iterable[str]) -> bool:
    left_set, right_set = set(left), set(right)
    return not left_set or not right_set or bool(left_set & right_set)


def _authority_confidence(authority: str) -> float:
    return {
        "authoritative": 1.0,
        "high": 0.85,
        "medium": 0.65,
        "low": 0.4,
        "heuristic": 0.2,
    }.get(authority, 0.5)


def _minimal_roots(items: list[Hypothesis]) -> list[Hypothesis]:
    by_id = {item.hypothesis_id: item for item in items}
    return [item for item in items if not item.parent_hypothesis_id or item.parent_hypothesis_id not in by_id]
