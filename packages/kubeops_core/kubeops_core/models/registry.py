from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from .base import SchemaModel


RegistryCategory = Literal[
    "canonical_type",
    "entity_type",
    "relationship_type",
    "invariant_family",
    "predicate_type",
    "disturbance_mechanism",
    "temporal_form",
    "mutation_type",
    "composition_operator",
    "scenario_family",
    "operational_profile",
    "evidence_intent",
    "collector",
    "causal_template",
    "action_type",
    "lifecycle_profile",
    "execution_policy",
    "knowledge_pack",
    "entity_classifier",
    "relationship_resolver",
    "verification_template",
    "redaction_rule",
    "pack_coverage",
    "organization",
    "workspace",
    "role",
    "fleet",
    "executor_agent",
    "retention_policy",
    "pack_trust_policy",
    "secret_provider",
    "audit_chain",
    "platform_backup",
    "maintenance_window",
    "scheduled_operation",
    "schedule_decision",
]


class RegistryEntry(SchemaModel):
    kind: ClassVar[str] = "RegistryEntry"

    registry_key: str
    category: RegistryCategory
    version: str = "1.0.0"
    title: str
    description: str = ""
    schema_ref: str | None = None
    capabilities: set[str] = Field(default_factory=set)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegistrySnapshot(SchemaModel):
    kind: ClassVar[str] = "RegistrySnapshot"

    entries: list[RegistryEntry]
    counts: dict[str, int]
