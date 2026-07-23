from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from .base import SchemaModel
from .enums import HealthStatus, InvariantFamily

EvidenceAuthority = Literal[
    "authoritative",
    "high",
    "medium",
    "low",
    "heuristic",
]
CostClass = Literal["negligible", "low", "medium", "high"]
RiskClass = Literal["R0", "R1", "R2", "R3", "R4", "R5"]


class EvidenceIntent(SchemaModel):
    """A semantic question that one or more read-only collectors may answer."""

    kind: ClassVar[str] = "EvidenceIntent"

    intent_id: str
    title: str = ""
    question: str
    questions_answered: list[str] = Field(default_factory=list)
    subject_ids: list[str] = Field(default_factory=list)
    required_fact_types: list[str] = Field(default_factory=list)
    preferred_collector_ids: list[str] = Field(default_factory=list)
    required_authority: EvidenceAuthority = "authoritative"
    maximum_age_seconds: int | None = Field(default=None, ge=0)
    cost_class: CostClass = "low"
    risk_class: RiskClass = "R0"
    stopping_condition: Literal[
        "first_authoritative_answer",
        "all_required_facts",
        "all_collectors",
    ] = "all_required_facts"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CollectorDefinition(SchemaModel):
    """A declarative, capability-aware read-only evidence collector contract."""

    kind: ClassVar[str] = "CollectorDefinition"

    collector_id: str
    title: str
    description: str = ""
    questions_answered: list[str] = Field(default_factory=list)
    fact_types: list[str] = Field(default_factory=list)
    supported_modes: set[Literal["simulation", "fixture", "live"]] = Field(
        default_factory=lambda: {"fixture", "live"}
    )
    required_capabilities: set[str] = Field(default_factory=set)
    supported_entity_types: set[str] = Field(default_factory=set)
    supported_planes: set[str] = Field(default_factory=set)
    required_inputs: set[str] = Field(default_factory=set)
    handler_id: str
    authority: EvidenceAuthority = "authoritative"
    cost_class: CostClass = "low"
    risk_class: RiskClass = "R0"
    estimated_duration_seconds: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceFact(SchemaModel):
    """A normalized, provenance-bearing fact used by deterministic diagnosis."""

    kind: ClassVar[str] = "EvidenceFact"

    evidence_id: str
    fact_type: str
    statement: str
    value: Any = None
    subject_ids: list[str] = Field(default_factory=list)
    intent_id: str | None = None
    collector_id: str
    observed_at_iso: str
    authority: EvidenceAuthority = "authoritative"
    freshness_seconds: int = Field(default=0, ge=0)
    source_artifact_ids: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class CollectorPlanStep(SchemaModel):
    kind: ClassVar[str] = "CollectorPlanStep"

    step_id: str
    collector_id: str
    intent_id: str
    subject_ids: list[str] = Field(default_factory=list)
    questions_answered: list[str] = Field(default_factory=list)
    expected_fact_types: list[str] = Field(default_factory=list)
    rationale: str
    score: float = 0.0
    dependencies: list[str] = Field(default_factory=list)


class EvidenceCollectionPlan(SchemaModel):
    kind: ClassVar[str] = "EvidenceCollectionPlan"

    plan_id: str
    incident_id: str | None = None
    environment_id: str
    snapshot_id: str
    created_at_iso: str
    intents: list[EvidenceIntent] = Field(default_factory=list)
    steps: list[CollectorPlanStep] = Field(default_factory=list)
    unresolved_intent_ids: list[str] = Field(default_factory=list)
    estimated_cost_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CollectorRunResult(SchemaModel):
    kind: ClassVar[str] = "CollectorRunResult"

    run_id: str
    step_id: str
    collector_id: str
    intent_id: str
    status: Literal["completed", "partial", "failed", "skipped"]
    started_at_iso: str
    completed_at_iso: str
    evidence: list[EvidenceFact] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Symptom(SchemaModel):
    kind: ClassVar[str] = "Symptom"

    symptom_id: str
    symptom_type: str
    statement: str
    subject_ids: list[str] = Field(default_factory=list)
    invariant_id: str | None = None
    invariant_family: InvariantFamily | None = None
    health_status: HealthStatus | None = None
    causal_role: Literal["initial", "upstream", "downstream", "unknown"] = "unknown"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    first_observed_at_seconds: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CausalTemplate(SchemaModel):
    """Reusable deterministic causal knowledge, independent of concrete resources."""

    kind: ClassVar[str] = "CausalTemplate"

    template_id: str
    family_id: str
    title: str
    claim_template: str
    parent_family_id: str | None = None
    invariant_families: set[InvariantFamily] = Field(default_factory=set)
    symptom_types: set[str] = Field(default_factory=set)
    supporting_fact_types: set[str] = Field(default_factory=set)
    contradicting_fact_types: set[str] = Field(default_factory=set)
    predicted_fact_types: set[str] = Field(default_factory=set)
    evidence_intent_ids: list[str] = Field(default_factory=list)
    specificity: int = Field(default=0, ge=0)
    generic: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CausalEdge(SchemaModel):
    kind: ClassVar[str] = "CausalEdge"

    edge_id: str
    source_id: str
    target_id: str
    relation: Literal[
        "causes",
        "explains",
        "propagates_to",
        "contradicts",
        "supports",
        "rules_out",
        "requires_probe",
    ]
    statement: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)


class Hypothesis(SchemaModel):
    kind: ClassVar[str] = "Hypothesis"

    hypothesis_id: str
    family_id: str
    claim: str
    template_id: str | None = None
    parent_hypothesis_id: str | None = None
    subject_ids: list[str] = Field(default_factory=list)
    status: Literal[
        "candidate",
        "supported",
        "proven",
        "contradicted",
        "ruled_out",
        "unresolved",
    ] = "candidate"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    explains_symptom_ids: list[str] = Field(default_factory=list)
    unexplained_symptom_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    required_probe_ids: list[str] = Field(default_factory=list)
    predictions: list[str] = Field(default_factory=list)
    score_components: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProbeIntent(SchemaModel):
    """A bounded read-only diagnostic operation selected for discriminative value."""

    kind: ClassVar[str] = "ProbeIntent"

    probe_id: str
    title: str
    evidence_intent_id: str
    applicable_hypothesis_ids: list[str] = Field(default_factory=list)
    discriminates_hypothesis_ids: list[str] = Field(default_factory=list)
    candidate_collector_ids: list[str] = Field(default_factory=list)
    expected_outcomes: dict[str, list[str]] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    rationale: str = ""
    information_gain_score: float = Field(default=0.0, ge=0.0)
    cost_score: float = Field(default=0.0, ge=0.0)
    risk_class: RiskClass = "R0"
    estimated_duration_seconds: int | None = Field(default=None, ge=0)
    status: Literal["recommended", "running", "completed", "skipped", "unavailable"] = "recommended"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProbePlan(SchemaModel):
    kind: ClassVar[str] = "ProbePlan"

    plan_id: str
    incident_id: str
    created_at_iso: str
    probes: list[ProbeIntent] = Field(default_factory=list)
    stopping_reason: str | None = None
    evidence_budget: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProbeRun(SchemaModel):
    kind: ClassVar[str] = "ProbeRun"

    probe_run_id: str
    incident_id: str
    probe: ProbeIntent
    collection_plan: EvidenceCollectionPlan
    collector_results: list[CollectorRunResult] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    status: Literal["completed", "partial", "failed", "skipped"]
    started_at_iso: str
    completed_at_iso: str
    hypothesis_changes: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiagnosisCertificate(SchemaModel):
    kind: ClassVar[str] = "DiagnosisCertificate"

    certificate_id: str
    incident_id: str
    issued_at_iso: str | None = None
    violated_invariant_ids: list[str] = Field(default_factory=list)
    causal_chain: list[str] = Field(default_factory=list)
    causal_edges: list[CausalEdge] = Field(default_factory=list)
    root_cause_hypothesis_ids: list[str] = Field(default_factory=list)
    ruled_out_hypothesis_ids: list[str] = Field(default_factory=list)
    unresolved_hypothesis_ids: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    status: Literal[
        "root_cause_identified",
        "failure_class_identified",
        "partial_causal_chain",
        "multiple_plausible_causes",
        "insufficient_evidence",
        "unknown_semantics",
    ]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    nearest_supported_family_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IncidentTimelineEntry(SchemaModel):
    kind: ClassVar[str] = "IncidentTimelineEntry"

    sequence: int = Field(ge=0)
    occurred_at_iso: str
    event_type: str
    title: str
    subject_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class IncidentInvestigation(SchemaModel):
    kind: ClassVar[str] = "IncidentInvestigation"

    incident_id: str
    environment_id: str
    snapshot_id: str
    profile_id: str
    title: str
    initial_symptom: str
    status: Literal[
        "open",
        "investigating",
        "diagnosed",
        "insufficient_evidence",
        "closed",
    ] = "open"
    created_at_iso: str
    updated_at_iso: str
    assessment_id: str | None = None
    violated_invariant_ids: list[str] = Field(default_factory=list)
    symptoms: list[Symptom] = Field(default_factory=list)
    evidence: list[EvidenceFact] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    probe_plan: ProbePlan | None = None
    probe_runs: list[ProbeRun] = Field(default_factory=list)
    causal_edges: list[CausalEdge] = Field(default_factory=list)
    timeline: list[IncidentTimelineEntry] = Field(default_factory=list)
    certificate: DiagnosisCertificate | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "IncidentInvestigation":
        evidence_ids = {item.evidence_id for item in self.evidence}
        symptom_ids = {item.symptom_id for item in self.symptoms}
        hypothesis_ids = {item.hypothesis_id for item in self.hypotheses}
        for symptom in self.symptoms:
            missing = set(symptom.evidence_ids) - evidence_ids
            if missing:
                raise ValueError(f"symptom {symptom.symptom_id} references unknown evidence {sorted(missing)}")
        for hypothesis in self.hypotheses:
            missing_symptoms = set(hypothesis.explains_symptom_ids) - symptom_ids
            missing_evidence = (
                set(hypothesis.supporting_evidence_ids)
                | set(hypothesis.contradicting_evidence_ids)
            ) - evidence_ids
            if missing_symptoms:
                raise ValueError(
                    f"hypothesis {hypothesis.hypothesis_id} references unknown symptoms {sorted(missing_symptoms)}"
                )
            if missing_evidence:
                raise ValueError(
                    f"hypothesis {hypothesis.hypothesis_id} references unknown evidence {sorted(missing_evidence)}"
                )
            if hypothesis.parent_hypothesis_id and hypothesis.parent_hypothesis_id not in hypothesis_ids:
                raise ValueError(
                    f"hypothesis {hypothesis.hypothesis_id} references unknown parent {hypothesis.parent_hypothesis_id}"
                )
        return self


class DiagnosticExpectation(SchemaModel):
    kind: ClassVar[str] = "DiagnosticExpectation"

    expected_family_ids: set[str] = Field(default_factory=set)
    acceptable_parent_family_ids: set[str] = Field(default_factory=set)
    required_statuses: set[str] = Field(default_factory=set)
    forbidden_family_ids: set[str] = Field(default_factory=set)
    maximum_probe_count: int | None = Field(default=None, ge=0)


class DiagnosticCaseResult(SchemaModel):
    kind: ClassVar[str] = "DiagnosticCaseResult"

    case_id: str
    scenario_id: str
    passed: bool
    certificate_status: str
    predicted_family_ids: list[str] = Field(default_factory=list)
    expected_family_ids: list[str] = Field(default_factory=list)
    probe_count: int = Field(default=0, ge=0)
    metrics: dict[str, float] = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)
    incident: IncidentInvestigation | None = None


class DiagnosticEvaluationReport(SchemaModel):
    kind: ClassVar[str] = "DiagnosticEvaluationReport"

    report_id: str
    created_at_iso: str
    case_results: list[DiagnosticCaseResult] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
