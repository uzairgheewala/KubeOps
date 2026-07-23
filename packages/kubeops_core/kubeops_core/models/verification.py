from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from .base import SchemaModel
from .enums import HealthStatus
from .invariant import TemporalRequirement
from .predicate import Predicate


class VerificationCondition(SchemaModel):
    kind: ClassVar[str] = "VerificationCondition"

    condition_id: str
    title: str
    predicate: Predicate
    temporal: TemporalRequirement = Field(default_factory=TemporalRequirement)
    level: Literal[
        "action_completion",
        "resource_convergence",
        "dependency_restoration",
        "semantic_health",
        "end_to_end",
        "stability",
        "side_effect_guard",
    ]
    required: bool = True


class VerificationResult(SchemaModel):
    kind: ClassVar[str] = "VerificationResult"

    result_id: str
    condition_id: str
    status: HealthStatus
    evaluated_at_seconds: int = Field(ge=0)
    explanation: str
    evidence_ids: list[str] = Field(default_factory=list)
    actual_value: Any = None


class RecoveryCertificate(SchemaModel):
    kind: ClassVar[str] = "RecoveryCertificate"

    certificate_id: str
    incident_id: str
    plan_id: str
    status: Literal[
        "recovered",
        "partially_recovered",
        "recovery_failed",
        "rollback_completed",
        "no_safe_recovery",
    ]
    restored_invariant_ids: list[str] = Field(default_factory=list)
    unresolved_invariant_ids: list[str] = Field(default_factory=list)
    action_receipt_ids: list[str] = Field(default_factory=list)
    verification_result_ids: list[str] = Field(default_factory=list)
    residual_risks: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
