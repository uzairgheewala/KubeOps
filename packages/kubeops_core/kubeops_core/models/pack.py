from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from .base import SchemaModel
from .diagnosis import CausalTemplate, CollectorDefinition, EvidenceIntent
from .health import OperationalProfileSpec
from .lifecycle import LifecycleProfile
from .planning import ActionTypeDefinition
from .verification import VerificationCondition

PackKind = Literal["core", "provider", "platform", "application", "integration"]
PackState = Literal["discovered", "resolved", "active", "incompatible", "blocked", "disabled"]
ContributionCategory = Literal[
    "entity_classifier",
    "relationship_resolver",
    "operational_profile",
    "evidence_intent",
    "collector",
    "causal_template",
    "action_type",
    "lifecycle_profile",
    "verification_template",
    "redaction_rule",
    "scenario_family",
]


class PackDependency(SchemaModel):
    kind: ClassVar[str] = "PackDependency"

    pack_id: str
    version_constraint: str = ">=0.0.0"
    optional: bool = False
    reason: str = ""


class PackCompatibility(SchemaModel):
    kind: ClassVar[str] = "PackCompatibility"

    kubeops_constraint: str = ">=0.5.0,<1.0.0"
    kubernetes_constraint: str | None = None
    python_constraint: str = ">=3.11"
    provider_constraints: dict[str, str] = Field(default_factory=dict)
    operating_systems: set[str] = Field(default_factory=set)
    architectures: set[str] = Field(default_factory=set)


class EntityClassifierRule(SchemaModel):
    kind: ClassVar[str] = "EntityClassifierRule"

    classifier_id: str
    priority: int = 0
    resource_kinds: set[str] = Field(default_factory=set)
    namespaces: set[str] = Field(default_factory=set)
    name_regex: str | None = None
    label_equals: dict[str, str] = Field(default_factory=dict)
    annotation_equals: dict[str, str] = Field(default_factory=dict)
    set_entity_type: str | None = None
    set_plane: str | None = None
    set_provider: str | None = None
    add_capabilities: set[str] = Field(default_factory=set)
    extension_namespace: str | None = None
    extension_values: dict[str, Any] = Field(default_factory=dict)


class RelationshipResolverRule(SchemaModel):
    kind: ClassVar[str] = "RelationshipResolverRule"

    resolver_id: str
    handler_id: Literal[
        "annotation_reference",
        "label_group",
        "named_kubernetes_resource",
        "component_dependency",
    ]
    relationship_type: str
    source_entity_types: set[str] = Field(default_factory=set)
    target_entity_types: set[str] = Field(default_factory=set)
    annotation_key: str | None = None
    label_key: str | None = None
    target_kind: str | None = None
    target_namespace: str | None = None
    target_name: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    contract: dict[str, Any] = Field(default_factory=dict)
    propagation: dict[str, Any] = Field(default_factory=dict)


class RedactionRule(SchemaModel):
    kind: ClassVar[str] = "RedactionRule"

    rule_id: str
    path_patterns: list[str] = Field(default_factory=list)
    key_patterns: list[str] = Field(default_factory=list)
    replacement: str = "<redacted>"
    applies_to_resource_kinds: set[str] = Field(default_factory=set)
    rationale: str = ""


class PackScenarioCoverage(SchemaModel):
    kind: ClassVar[str] = "PackScenarioCoverage"

    family_ids: set[str] = Field(default_factory=set)
    invariant_families: set[str] = Field(default_factory=set)
    disturbance_mechanisms: set[str] = Field(default_factory=set)
    topology_patterns: set[str] = Field(default_factory=set)
    support_level: Literal[
        "representable",
        "detectable",
        "diagnosable",
        "guidance",
        "executable",
        "verified",
    ] = "representable"


class PackContributions(SchemaModel):
    kind: ClassVar[str] = "PackContributions"

    entity_classifiers: list[EntityClassifierRule] = Field(default_factory=list)
    relationship_resolvers: list[RelationshipResolverRule] = Field(default_factory=list)
    operational_profiles: list[OperationalProfileSpec] = Field(default_factory=list)
    evidence_intents: list[EvidenceIntent] = Field(default_factory=list)
    collectors: list[CollectorDefinition] = Field(default_factory=list)
    causal_templates: list[CausalTemplate] = Field(default_factory=list)
    action_types: list[ActionTypeDefinition] = Field(default_factory=list)
    lifecycle_profiles: list[LifecycleProfile] = Field(default_factory=list)
    verification_templates: list[VerificationCondition] = Field(default_factory=list)
    redaction_rules: list[RedactionRule] = Field(default_factory=list)
    scenario_coverage: list[PackScenarioCoverage] = Field(default_factory=list)

    def counts(self) -> dict[str, int]:
        payload = self.model_dump(mode="python")
        return {key: len(value) for key, value in payload.items() if isinstance(value, list)}


class KnowledgePackManifest(SchemaModel):
    kind: ClassVar[str] = "KnowledgePackManifest"

    pack_id: str
    version: str
    title: str
    pack_kind: PackKind
    description: str = ""
    api_version: str = "kubeops.io/pack/v1"
    priority: int = 0
    dependencies: list[PackDependency] = Field(default_factory=list)
    conflicts_with: set[str] = Field(default_factory=set)
    compatibility: PackCompatibility = Field(default_factory=PackCompatibility)
    capabilities: set[str] = Field(default_factory=set)
    supported_entity_types: set[str] = Field(default_factory=set)
    contributions: PackContributions = Field(default_factory=PackContributions)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dependencies(self) -> "KnowledgePackManifest":
        dependency_ids = [item.pack_id for item in self.dependencies]
        if self.pack_id in dependency_ids:
            raise ValueError("a pack cannot depend on itself")
        if len(dependency_ids) != len(set(dependency_ids)):
            raise ValueError("pack dependencies must be unique")
        if self.pack_id in self.conflicts_with:
            raise ValueError("a pack cannot conflict with itself")
        return self


class PackValidationIssue(SchemaModel):
    kind: ClassVar[str] = "PackValidationIssue"

    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    pack_id: str | None = None
    contribution_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class PackStatus(SchemaModel):
    kind: ClassVar[str] = "PackStatus"

    pack_id: str
    version: str
    state: PackState
    source: str
    enabled: bool = True
    resolved_dependencies: list[str] = Field(default_factory=list)
    contribution_counts: dict[str, int] = Field(default_factory=dict)
    issues: list[PackValidationIssue] = Field(default_factory=list)
    manifest_hash: str


class PackResolution(SchemaModel):
    kind: ClassVar[str] = "PackResolution"

    resolution_id: str
    created_at_iso: str
    requested_pack_ids: list[str]
    ordered_pack_ids: list[str]
    active_pack_ids: list[str]
    blocked_pack_ids: list[str]
    statuses: list[PackStatus]
    issues: list[PackValidationIssue] = Field(default_factory=list)
    contribution_counts: dict[str, int] = Field(default_factory=dict)


class PackCoverageReport(SchemaModel):
    kind: ClassVar[str] = "PackCoverageReport"

    generated_at_iso: str
    active_pack_ids: list[str]
    by_pack: dict[str, list[PackScenarioCoverage]] = Field(default_factory=dict)
    family_support: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    invariant_support: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)
