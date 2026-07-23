from __future__ import annotations

from kubeops_core.models.enums import (
    DisturbanceMechanism,
    InvariantFamily,
    OperationalPlane,
    TemporalForm,
)
from kubeops_core.models.registry import RegistryEntry

from .catalog import RegistryCatalog


CANONICAL_TYPES = [
    "OperationalEntity",
    "Relationship",
    "OperationalObjective",
    "OperationalProfile",
    "InvariantDefinition",
    "Observation",
    "ObservationProfile",
    "EvidenceIntent",
    "CollectorDefinition",
    "EvidenceFact",
    "EvidenceCollectionPlan",
    "CollectorRunResult",
    "Symptom",
    "CausalTemplate",
    "CausalEdge",
    "Hypothesis",
    "ProbeIntent",
    "ProbePlan",
    "ProbeRun",
    "IncidentInvestigation",
    "ScenarioFamily",
    "ScenarioInstance",
    "ScenarioComposition",
    "ActionTypeDefinition",
    "ActionInstance",
    "ExecutionPolicy",
    "PolicyDecision",
    "RecoveryPlan",
    "VerificationCondition",
    "VerificationResult",
    "DiagnosisCertificate",
    "DiagnosticExpectation",
    "DiagnosticCaseResult",
    "DiagnosticEvaluationReport",
    "RecoveryCertificate",
    "LifecycleActionTemplate",
    "LifecycleStageDefinition",
    "LifecycleProfile",
    "ApprovalRecord",
    "ActionReceipt",
    "ExecutionCheckpoint",
    "OperationEvent",
    "OperationRun",
    "SimulationRun",
    "RunArtifact",
    "OrganizationDefinition",
    "WorkspaceDefinition",
    "RoleGrant",
    "AuthorizationRequest",
    "AuthorizationDecision",
    "ScopeBinding",
    "FleetMember",
    "FleetDependency",
    "FleetDefinition",
    "FleetEnvironmentStatus",
    "CommonCauseFinding",
    "FleetAssessment",
    "FleetOperationWave",
    "FleetOperationPlan",
    "ExecutorAgentDefinition",
    "ExecutorHeartbeat",
    "ExecutionTask",
    "TaskLease",
    "DispatchDecision",
    "RateLimitRule",
    "ConcurrencyRule",
    "GovernanceDecision",
    "RetentionPolicy",
    "RetentionCandidate",
    "RetentionPlan",
    "AuditEvent",
    "AuditChainVerification",
    "AuditExport",
    "SecretReference",
    "SecretResolutionReceipt",
    "PackSignature",
    "PackTrustPolicy",
    "PackVerificationResult",
    "BackupComponent",
    "ControlPlaneBackupManifest",
    "ControlPlaneRestorePlan",
    "RestoreStep",
    "UpgradeReadinessCheck",
    "UpgradeReadinessReport",
    "MaintenanceWindow",
    "ScheduledOperation",
    "ScheduleDecision",
]

RELATIONSHIP_TYPES = [
    "contains",
    "owns",
    "controls",
    "selects",
    "binds",
    "mounts",
    "references",
    "requires_for_startup",
    "requires_for_readiness",
    "requires_for_liveness",
    "requires_for_service",
    "requires_for_shutdown",
    "requires_for_recovery",
    "connects_to",
    "routes_to",
    "resolves_through",
    "authenticates_to",
    "authorizes_against",
    "reconciles",
    "schedules",
    "admits",
    "monitors",
]

PREDICATE_TYPES = [
    "field_equals",
    "field_not_equals",
    "field_exists",
    "field_gte",
    "field_lte",
    "all_of",
    "any_of",
    "not",
]

MUTATION_TYPES = ["set_state", "delete_entity", "create_entity"]
COMPOSITION_OPERATORS = [
    "concurrent",
    "sequential",
    "conditional",
    "masking",
    "recovery_interference",
]


def build_builtin_catalog() -> RegistryCatalog:
    catalog = RegistryCatalog()
    for canonical_type in CANONICAL_TYPES:
        catalog.register(
            RegistryEntry(
                registry_key=canonical_type,
                category="canonical_type",
                title=canonical_type,
                description="Versioned KubeOps canonical IR schema.",
                schema_ref=f"/api/v1/schemas/{canonical_type}",
            )
        )
    for plane in OperationalPlane:
        catalog.register(
            RegistryEntry(
                registry_key=plane.value,
                category="entity_type",
                title=plane.value.replace("_", " ").title(),
                description="Built-in operational-plane entity category.",
            )
        )
    for relationship in RELATIONSHIP_TYPES:
        catalog.register(
            RegistryEntry(
                registry_key=relationship,
                category="relationship_type",
                title=relationship.replace("_", " ").title(),
            )
        )
    for family in InvariantFamily:
        catalog.register(
            RegistryEntry(
                registry_key=family.value,
                category="invariant_family",
                title=family.value.replace("_", " ").title(),
            )
        )
    for predicate in PREDICATE_TYPES:
        catalog.register(
            RegistryEntry(
                registry_key=predicate,
                category="predicate_type",
                title=predicate.replace("_", " ").title(),
                schema_ref="#/$defs/Predicate",
            )
        )
    for mechanism in DisturbanceMechanism:
        catalog.register(
            RegistryEntry(
                registry_key=mechanism.value,
                category="disturbance_mechanism",
                title=mechanism.value.replace("_", " ").title(),
            )
        )
    for temporal in TemporalForm:
        catalog.register(
            RegistryEntry(
                registry_key=temporal.value,
                category="temporal_form",
                title=temporal.value.replace("_", " ").title(),
            )
        )
    for mutation in MUTATION_TYPES:
        catalog.register(
            RegistryEntry(
                registry_key=mutation,
                category="mutation_type",
                title=mutation.replace("_", " ").title(),
            )
        )
    for operator in COMPOSITION_OPERATORS:
        catalog.register(
            RegistryEntry(
                registry_key=operator,
                category="composition_operator",
                title=operator.replace("_", " ").title(),
            )
        )
    for entry in [
        RegistryEntry(
            registry_key="maintenance-window",
            category="maintenance_window",
            title="Maintenance Window",
            description="Recurring timezone-aware operation eligibility window.",
            schema_ref="/api/v1/schemas/MaintenanceWindow",
        ),
        RegistryEntry(
            registry_key="scheduled-operation",
            category="scheduled_operation",
            title="Scheduled Operation",
            description="Durable request to materialize a normal governed operation or fleet plan.",
            schema_ref="/api/v1/schemas/ScheduledOperation",
        ),
        RegistryEntry(
            registry_key="schedule-decision",
            category="schedule_decision",
            title="Schedule Decision",
            description="Deterministic ready, delay, deny, expiry, or terminal scheduling result.",
            schema_ref="/api/v1/schemas/ScheduleDecision",
        ),
    ]:
        catalog.register(entry)
    return catalog
