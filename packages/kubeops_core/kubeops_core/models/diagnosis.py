from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from .base import SchemaModel


class EvidenceIntent(SchemaModel):
    """A semantic question that one or more collectors may answer."""

    kind: ClassVar[str] = "EvidenceIntent"

    intent_id: str
    question: str
    questions_answered: list[str] = Field(default_factory=list)
    subject_ids: list[str] = Field(default_factory=list)
    required_authority: str = "authoritative"
    maximum_age_seconds: int | None = Field(default=None, ge=0)
    cost_class: Literal["negligible", "low", "medium", "high"] = "low"
    risk_class: Literal["R0", "R1", "R2", "R3", "R4", "R5"] = "R0"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Symptom(SchemaModel):
    kind: ClassVar[str] = "Symptom"

    symptom_id: str
    symptom_type: str
    subject_ids: list[str] = Field(default_factory=list)
    statement: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    first_observed_at_seconds: int | None = Field(default=None, ge=0)


class Hypothesis(SchemaModel):
    kind: ClassVar[str] = "Hypothesis"

    hypothesis_id: str
    family_id: str
    claim: str
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
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    required_probe_ids: list[str] = Field(default_factory=list)
    predictions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProbeIntent(SchemaModel):
    """A bounded diagnostic operation selected for discriminative value."""

    kind: ClassVar[str] = "ProbeIntent"

    probe_id: str
    title: str
    evidence_intent_id: str
    applicable_hypothesis_ids: list[str] = Field(default_factory=list)
    discriminates_hypothesis_ids: list[str] = Field(default_factory=list)
    expected_outcomes: dict[str, list[str]] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    risk_class: Literal["R0", "R1", "R2", "R3", "R4", "R5"] = "R0"
    estimated_duration_seconds: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiagnosisCertificate(SchemaModel):
    kind: ClassVar[str] = "DiagnosisCertificate"

    certificate_id: str
    incident_id: str
    violated_invariant_ids: list[str] = Field(default_factory=list)
    causal_chain: list[str] = Field(default_factory=list)
    root_cause_hypothesis_ids: list[str] = Field(default_factory=list)
    ruled_out_hypothesis_ids: list[str] = Field(default_factory=list)
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
    metadata: dict[str, Any] = Field(default_factory=dict)
