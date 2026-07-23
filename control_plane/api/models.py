from __future__ import annotations

from django.db import models




class OrganizationRecord(models.Model):
    organization_id = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    active = models.BooleanField(default=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "organization_id"]


class WorkspaceRecord(models.Model):
    workspace_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="workspaces")
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    active = models.BooleanField(default=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["organization", "name", "workspace_id"]
        constraints = [models.UniqueConstraint(fields=["organization", "slug"], name="unique_workspace_slug_per_org")]


class RoleGrantRecord(models.Model):
    grant_id = models.CharField(max_length=255, unique=True)
    principal_id = models.CharField(max_length=255)
    role = models.CharField(max_length=32)
    scope_type = models.CharField(max_length=32)
    scope_id = models.CharField(max_length=255)
    active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField()
    granted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["principal_id", "scope_type", "scope_id", "role"]
        indexes = [
            models.Index(fields=["principal_id", "active"]),
            models.Index(fields=["scope_type", "scope_id", "active"]),
        ]

class ScenarioFamilyRecord(models.Model):
    family_id = models.CharField(max_length=255, unique=True)
    version = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    parent_family_id = models.CharField(max_length=255, null=True, blank=True)
    content_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    source_path = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["family_id"]


class ScenarioRunRecord(models.Model):
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="scenario_runs", null=True, blank=True)
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="scenario_runs", null=True, blank=True)
    run_id = models.CharField(max_length=255, unique=True)
    scenario_id = models.CharField(max_length=255)
    family_id = models.CharField(max_length=255)
    status = models.CharField(max_length=32)
    scenario_payload = models.JSONField()
    run_payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["family_id", "created_at"]),
            models.Index(fields=["workspace", "created_at"]),
        ]


class EnvironmentRecord(models.Model):
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.PROTECT, related_name="environments", null=True, blank=True)
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.PROTECT, related_name="environments", null=True, blank=True)
    environment_id = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    environment_class = models.CharField(max_length=32)
    provider = models.CharField(max_length=128)
    cluster_provider = models.CharField(max_length=128)
    host_provider = models.CharField(max_length=128, null=True, blank=True)
    criticality = models.CharField(max_length=64, default="standard")
    fingerprint = models.CharField(max_length=64)
    payload = models.JSONField()
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "environment_id"]
        indexes = [models.Index(fields=["environment_class", "active"])]


class AccessValidationRecord(models.Model):
    validation_id = models.CharField(max_length=255, unique=True)
    environment = models.ForeignKey(EnvironmentRecord, on_delete=models.CASCADE, related_name="access_validations")
    access_method_id = models.CharField(max_length=255)
    status = models.CharField(max_length=32)
    target_fingerprint = models.CharField(max_length=255)
    payload = models.JSONField()
    checked_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-checked_at"]
        indexes = [models.Index(fields=["environment", "checked_at"])]


class EnvironmentSnapshotRecord(models.Model):
    snapshot_id = models.CharField(max_length=255, unique=True)
    environment = models.ForeignKey(EnvironmentRecord, on_delete=models.CASCADE, related_name="snapshots")
    status = models.CharField(max_length=32)
    source_type = models.CharField(max_length=32)
    source_fingerprint = models.CharField(max_length=255)
    captured_at = models.DateTimeField()
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField()
    content_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    summary = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-captured_at"]
        indexes = [
            models.Index(fields=["environment", "captured_at"]),
            models.Index(fields=["status", "captured_at"]),
        ]


class SnapshotEntityRecord(models.Model):
    snapshot = models.ForeignKey(EnvironmentSnapshotRecord, on_delete=models.CASCADE, related_name="entities")
    entity_id = models.CharField(max_length=512)
    entity_type = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    plane = models.CharField(max_length=64)
    namespace = models.CharField(max_length=255, null=True, blank=True)
    provider = models.CharField(max_length=128, null=True, blank=True)
    labels = models.JSONField(default=dict)
    desired_state = models.JSONField(default=dict)
    observed_state = models.JSONField(default=dict)
    content_hash = models.CharField(max_length=64)
    payload = models.JSONField()

    class Meta:
        ordering = ["plane", "namespace", "entity_type", "name"]
        constraints = [models.UniqueConstraint(fields=["snapshot", "entity_id"], name="unique_snapshot_entity")]
        indexes = [
            models.Index(fields=["snapshot", "entity_type"]),
            models.Index(fields=["snapshot", "namespace"]),
            models.Index(fields=["snapshot", "plane"]),
        ]


class SnapshotRelationshipRecord(models.Model):
    snapshot = models.ForeignKey(EnvironmentSnapshotRecord, on_delete=models.CASCADE, related_name="relationships")
    relationship_id = models.CharField(max_length=768)
    source_id = models.CharField(max_length=512)
    target_id = models.CharField(max_length=512)
    relationship_type = models.CharField(max_length=128)
    confidence = models.FloatField(default=1.0)
    provenance = models.CharField(max_length=255)
    content_hash = models.CharField(max_length=64)
    payload = models.JSONField()

    class Meta:
        ordering = ["relationship_type", "relationship_id"]
        constraints = [models.UniqueConstraint(fields=["snapshot", "relationship_id"], name="unique_snapshot_relationship")]
        indexes = [
            models.Index(fields=["snapshot", "source_id"]),
            models.Index(fields=["snapshot", "target_id"]),
            models.Index(fields=["snapshot", "relationship_type"]),
        ]


class OperationalProfileRecord(models.Model):
    profile_id = models.CharField(max_length=255, unique=True)
    version = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    source_path = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["profile_id"]


class ProfileAssessmentRecord(models.Model):
    assessment_id = models.CharField(max_length=255, unique=True)
    snapshot = models.ForeignKey(EnvironmentSnapshotRecord, on_delete=models.CASCADE, related_name="assessments")
    profile_id = models.CharField(max_length=255)
    profile_version = models.CharField(max_length=64)
    status = models.CharField(max_length=32)
    payload = models.JSONField()
    evaluated_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["profile_id"]
        constraints = [models.UniqueConstraint(fields=["snapshot", "profile_id"], name="unique_snapshot_profile_assessment")]
        indexes = [models.Index(fields=["profile_id", "status"])]


class ArtifactRecord(models.Model):
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="artifacts", null=True, blank=True)
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="artifacts", null=True, blank=True)
    artifact_id = models.CharField(max_length=255, unique=True)
    run = models.ForeignKey(ScenarioRunRecord, on_delete=models.CASCADE, related_name="artifacts", null=True, blank=True)
    scope_type = models.CharField(max_length=64, default="simulation_run")
    scope_id = models.CharField(max_length=255, default="")
    artifact_type = models.CharField(max_length=64)
    content_hash = models.CharField(max_length=64)
    media_type = models.CharField(max_length=128)
    storage_path = models.TextField()
    derived_from = models.JSONField(default=list)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["scope_type", "scope_id"]),
            models.Index(fields=["workspace", "created_at"]),
        ]


class OperationEventRecord(models.Model):
    run = models.ForeignKey(ScenarioRunRecord, on_delete=models.CASCADE, related_name="events")
    sequence = models.PositiveIntegerField()
    event_type = models.CharField(max_length=128)
    occurred_at_seconds = models.PositiveIntegerField()
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["run", "sequence"], name="unique_run_event_sequence")
        ]


class IncidentRecord(models.Model):
    incident_id = models.CharField(max_length=255, unique=True)
    environment = models.ForeignKey(EnvironmentRecord, on_delete=models.CASCADE, related_name="incidents")
    snapshot = models.ForeignKey(EnvironmentSnapshotRecord, on_delete=models.CASCADE, related_name="incidents")
    profile_id = models.CharField(max_length=255)
    title = models.CharField(max_length=512)
    initial_symptom = models.TextField()
    status = models.CharField(max_length=64)
    certificate_status = models.CharField(max_length=64, null=True, blank=True)
    confidence = models.FloatField(default=0.0)
    payload = models.JSONField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    persisted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["environment", "updated_at"]),
            models.Index(fields=["status", "updated_at"]),
            models.Index(fields=["profile_id", "certificate_status"]),
        ]


class EvidenceFactRecord(models.Model):
    evidence_id = models.CharField(max_length=255)
    incident = models.ForeignKey(IncidentRecord, on_delete=models.CASCADE, related_name="evidence_facts")
    fact_type = models.CharField(max_length=255)
    collector_id = models.CharField(max_length=255)
    authority = models.CharField(max_length=32)
    subject_ids = models.JSONField(default=list)
    observed_at = models.DateTimeField()
    payload = models.JSONField()

    class Meta:
        ordering = ["fact_type", "evidence_id"]
        constraints = [models.UniqueConstraint(fields=["incident", "evidence_id"], name="unique_incident_evidence")]
        indexes = [
            models.Index(fields=["incident", "fact_type"]),
            models.Index(fields=["collector_id", "authority"]),
        ]


class HypothesisRecord(models.Model):
    hypothesis_id = models.CharField(max_length=255)
    incident = models.ForeignKey(IncidentRecord, on_delete=models.CASCADE, related_name="hypotheses")
    family_id = models.CharField(max_length=255)
    status = models.CharField(max_length=32)
    confidence = models.FloatField(default=0.0)
    subject_ids = models.JSONField(default=list)
    payload = models.JSONField()

    class Meta:
        ordering = ["-confidence", "family_id"]
        constraints = [models.UniqueConstraint(fields=["incident", "hypothesis_id"], name="unique_incident_hypothesis")]
        indexes = [
            models.Index(fields=["incident", "status"]),
            models.Index(fields=["family_id", "status"]),
        ]


class ProbeRunRecord(models.Model):
    probe_run_id = models.CharField(max_length=255, unique=True)
    incident = models.ForeignKey(IncidentRecord, on_delete=models.CASCADE, related_name="probe_runs")
    probe_id = models.CharField(max_length=255)
    intent_id = models.CharField(max_length=255)
    status = models.CharField(max_length=32)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField()
    payload = models.JSONField()

    class Meta:
        ordering = ["started_at"]
        indexes = [models.Index(fields=["incident", "started_at"])]


class IncidentTimelineRecord(models.Model):
    incident = models.ForeignKey(IncidentRecord, on_delete=models.CASCADE, related_name="timeline_entries")
    sequence = models.PositiveIntegerField()
    event_type = models.CharField(max_length=128)
    occurred_at = models.DateTimeField()
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["incident", "sequence"], name="unique_incident_timeline_sequence")
        ]


class DiagnosisCertificateRecord(models.Model):
    certificate_id = models.CharField(max_length=255, unique=True)
    incident = models.OneToOneField(IncidentRecord, on_delete=models.CASCADE, related_name="diagnosis_certificate")
    status = models.CharField(max_length=64)
    confidence = models.FloatField(default=0.0)
    issued_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField()

    class Meta:
        ordering = ["-issued_at"]


class LifecycleProfileRecord(models.Model):
    profile_id = models.CharField(max_length=255, unique=True)
    version = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    operation_type = models.CharField(max_length=32)
    target_operational_profile_id = models.CharField(max_length=255)
    content_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    source_path = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["profile_id"]


class ExecutionPolicyRecord(models.Model):
    policy_id = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=255)
    content_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    source_path = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["policy_id"]


class OperationRecord(models.Model):
    operation_id = models.CharField(max_length=255, unique=True)
    environment = models.ForeignKey(EnvironmentRecord, on_delete=models.CASCADE, related_name="operations")
    snapshot = models.ForeignKey(EnvironmentSnapshotRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="operations")
    incident = models.ForeignKey(IncidentRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="operations")
    operation_type = models.CharField(max_length=32)
    objective_id = models.CharField(max_length=255)
    status = models.CharField(max_length=64)
    mode = models.CharField(max_length=32)
    plan_id = models.CharField(max_length=255)
    policy_id = models.CharField(max_length=255, null=True, blank=True)
    certificate_status = models.CharField(max_length=64, null=True, blank=True)
    payload = models.JSONField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    persisted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["environment", "updated_at"]),
            models.Index(fields=["status", "updated_at"]),
            models.Index(fields=["operation_type", "status"]),
        ]


class OperationPolicyDecisionRecord(models.Model):
    decision_id = models.CharField(max_length=255)
    operation = models.ForeignKey(OperationRecord, on_delete=models.CASCADE, related_name="policy_decisions")
    action_id = models.CharField(max_length=255)
    policy_id = models.CharField(max_length=255)
    outcome = models.CharField(max_length=32)
    payload = models.JSONField()

    class Meta:
        ordering = ["action_id"]
        constraints = [models.UniqueConstraint(fields=["operation", "decision_id"], name="unique_operation_policy_decision")]


class OperationApprovalRecord(models.Model):
    approval_id = models.CharField(max_length=255, unique=True)
    operation = models.ForeignKey(OperationRecord, on_delete=models.CASCADE, related_name="approvals")
    action_id = models.CharField(max_length=255, null=True, blank=True)
    approver_id = models.CharField(max_length=255)
    decision = models.CharField(max_length=16)
    granted_at = models.DateTimeField()
    payload = models.JSONField()

    class Meta:
        ordering = ["granted_at"]


class ActionReceiptRecord(models.Model):
    receipt_id = models.CharField(max_length=255, unique=True)
    operation = models.ForeignKey(OperationRecord, on_delete=models.CASCADE, related_name="action_receipts")
    action_id = models.CharField(max_length=255)
    action_type_id = models.CharField(max_length=255)
    executor_id = models.CharField(max_length=255)
    status = models.CharField(max_length=32)
    attempt = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField()
    idempotency_key = models.CharField(max_length=512, null=True, blank=True)
    payload = models.JSONField()

    class Meta:
        ordering = ["started_at", "receipt_id"]
        indexes = [models.Index(fields=["operation", "action_id"]), models.Index(fields=["idempotency_key", "status"])]


class OperationTimelineRecord(models.Model):
    operation = models.ForeignKey(OperationRecord, on_delete=models.CASCADE, related_name="timeline_entries")
    sequence = models.PositiveIntegerField()
    event_type = models.CharField(max_length=128)
    action_id = models.CharField(max_length=255, null=True, blank=True)
    occurred_at = models.DateTimeField()
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["sequence"]
        constraints = [models.UniqueConstraint(fields=["operation", "sequence"], name="unique_operation_timeline_sequence")]


class ExecutionCheckpointRecord(models.Model):
    checkpoint_id = models.CharField(max_length=255, unique=True)
    operation = models.ForeignKey(OperationRecord, on_delete=models.CASCADE, related_name="checkpoints")
    state_hash = models.CharField(max_length=64)
    resumable = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    payload = models.JSONField()

    class Meta:
        ordering = ["created_at"]


class OperationVerificationRecord(models.Model):
    result_id = models.CharField(max_length=255, unique=True)
    operation = models.ForeignKey(OperationRecord, on_delete=models.CASCADE, related_name="verification_results")
    condition_id = models.CharField(max_length=255)
    status = models.CharField(max_length=32)
    payload = models.JSONField()

    class Meta:
        ordering = ["condition_id"]


class RecoveryCertificateRecord(models.Model):
    certificate_id = models.CharField(max_length=255, unique=True)
    operation = models.OneToOneField(OperationRecord, on_delete=models.CASCADE, related_name="recovery_certificate")
    status = models.CharField(max_length=64)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class KnowledgePackRecord(models.Model):
    pack_id = models.CharField(max_length=255, unique=True)
    version = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    pack_kind = models.CharField(max_length=32)
    state = models.CharField(max_length=32, default="discovered")
    enabled = models.BooleanField(default=True)
    source_path = models.TextField(blank=True)
    manifest_hash = models.CharField(max_length=64)
    contribution_counts = models.JSONField(default=dict)
    capabilities = models.JSONField(default=list)
    payload = models.JSONField()
    validation_issues = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["pack_kind", "pack_id"]
        indexes = [
            models.Index(fields=["state", "enabled"]),
            models.Index(fields=["pack_kind", "pack_id"]),
        ]


class FleetRecord(models.Model):
    fleet_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="fleets")
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="fleets")
    name = models.CharField(max_length=255)
    max_parallel_operations = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workspace", "name", "fleet_id"]


class FleetMembershipRecord(models.Model):
    fleet = models.ForeignKey(FleetRecord, on_delete=models.CASCADE, related_name="memberships")
    environment = models.ForeignKey(EnvironmentRecord, on_delete=models.CASCADE, related_name="fleet_memberships")
    criticality = models.CharField(max_length=64, default="standard")
    failure_domain = models.CharField(max_length=255, null=True, blank=True)
    payload = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["fleet", "environment"], name="unique_fleet_environment")]
        ordering = ["fleet", "environment"]


class FleetDependencyRecord(models.Model):
    dependency_id = models.CharField(max_length=255, unique=True)
    fleet = models.ForeignKey(FleetRecord, on_delete=models.CASCADE, related_name="dependencies")
    source_environment = models.ForeignKey(EnvironmentRecord, on_delete=models.CASCADE, related_name="fleet_dependencies_out")
    target_environment = models.ForeignKey(EnvironmentRecord, on_delete=models.CASCADE, related_name="fleet_dependencies_in")
    relationship_type = models.CharField(max_length=128)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["fleet", "dependency_id"]


class FleetAssessmentRecord(models.Model):
    assessment_id = models.CharField(max_length=255, unique=True)
    fleet = models.ForeignKey(FleetRecord, on_delete=models.CASCADE, related_name="assessments")
    status = models.CharField(max_length=32)
    generated_at = models.DateTimeField()
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-generated_at"]
        indexes = [models.Index(fields=["fleet", "generated_at"]), models.Index(fields=["status", "generated_at"])]


class ExecutorAgentRecord(models.Model):
    agent_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="executor_agents")
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="executor_agents")
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=32)
    capabilities = models.JSONField(default=list)
    supported_executor_ids = models.JSONField(default=list)
    environment_ids = models.JSONField(default=list)
    max_concurrency = models.PositiveIntegerField(default=1)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    public_identity = models.CharField(max_length=512, null=True, blank=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workspace", "name", "agent_id"]
        indexes = [models.Index(fields=["workspace", "status"]), models.Index(fields=["status", "last_heartbeat_at"])]


class ExecutorHeartbeatRecord(models.Model):
    heartbeat_id = models.CharField(max_length=255, unique=True)
    agent = models.ForeignKey(ExecutorAgentRecord, on_delete=models.CASCADE, related_name="heartbeats")
    status = models.CharField(max_length=32)
    occurred_at = models.DateTimeField()
    payload = models.JSONField()

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["agent", "occurred_at"])]


class ExecutionTaskRecord(models.Model):
    task_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="execution_tasks")
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="execution_tasks")
    operation = models.ForeignKey(OperationRecord, on_delete=models.CASCADE, related_name="execution_tasks")
    environment = models.ForeignKey(EnvironmentRecord, on_delete=models.CASCADE, related_name="execution_tasks")
    action_id = models.CharField(max_length=255)
    action_type_id = models.CharField(max_length=255)
    executor_id = models.CharField(max_length=255)
    status = models.CharField(max_length=32)
    priority = models.IntegerField(default=0)
    assigned_agent = models.ForeignKey(ExecutorAgentRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tasks")
    payload_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        ordering = ["-priority", "created_at"]
        indexes = [models.Index(fields=["workspace", "status", "priority"]), models.Index(fields=["operation", "action_id"])]


class TaskLeaseRecord(models.Model):
    lease_id = models.CharField(max_length=255, unique=True)
    task = models.ForeignKey(ExecutionTaskRecord, on_delete=models.CASCADE, related_name="leases")
    agent = models.ForeignKey(ExecutorAgentRecord, on_delete=models.CASCADE, related_name="task_leases")
    status = models.CharField(max_length=32)
    nonce_hash = models.CharField(max_length=64)
    acquired_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    heartbeat_at = models.DateTimeField()
    payload = models.JSONField()

    class Meta:
        ordering = ["-acquired_at"]
        indexes = [models.Index(fields=["task", "status"]), models.Index(fields=["agent", "status", "expires_at"])]


class AuditEventRecord(models.Model):
    event_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="audit_events")
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="audit_events")
    sequence = models.PositiveBigIntegerField()
    principal_id = models.CharField(max_length=255)
    action = models.CharField(max_length=255)
    resource_type = models.CharField(max_length=128)
    resource_id = models.CharField(max_length=512)
    outcome = models.CharField(max_length=64)
    previous_hash = models.CharField(max_length=64, null=True, blank=True)
    event_hash = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()
    payload = models.JSONField()

    class Meta:
        ordering = ["workspace", "sequence"]
        constraints = [models.UniqueConstraint(fields=["workspace", "sequence"], name="unique_workspace_audit_sequence")]
        indexes = [models.Index(fields=["workspace", "occurred_at"]), models.Index(fields=["principal_id", "occurred_at"])]


class RateLimitRuleRecord(models.Model):
    rule_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="rate_limit_rules")
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="rate_limit_rules")
    operation = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workspace", "operation", "rule_id"]
        indexes = [models.Index(fields=["workspace", "operation", "enabled"])]


class ConcurrencyRuleRecord(models.Model):
    rule_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="concurrency_rules")
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="concurrency_rules")
    operation_type = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workspace", "operation_type", "rule_id"]
        indexes = [models.Index(fields=["workspace", "operation_type", "enabled"])]


class GovernanceUsageRecord(models.Model):
    usage_id = models.CharField(max_length=255, unique=True)
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="governance_usage")
    operation = models.CharField(max_length=255)
    target_id = models.CharField(max_length=512, null=True, blank=True)
    decision_id = models.CharField(max_length=255)
    occurred_at = models.DateTimeField()
    terminal = models.BooleanField(default=False)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["workspace", "operation", "occurred_at"]),
            models.Index(fields=["workspace", "operation", "target_id", "terminal"]),
        ]


class MaintenanceWindowRecord(models.Model):
    window_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="maintenance_windows")
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="maintenance_windows")
    enabled = models.BooleanField(default=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workspace", "window_id"]
        indexes = [models.Index(fields=["workspace", "enabled"])]


class ScheduledOperationRecord(models.Model):
    schedule_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="scheduled_operations")
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="scheduled_operations")
    target_type = models.CharField(max_length=32)
    target_id = models.CharField(max_length=255)
    operation_type = models.CharField(max_length=255)
    status = models.CharField(max_length=32)
    not_before = models.DateTimeField(null=True, blank=True)
    deadline = models.DateTimeField(null=True, blank=True)
    maintenance_window = models.ForeignKey(MaintenanceWindowRecord, null=True, blank=True, on_delete=models.PROTECT, related_name="scheduled_operations")
    operation = models.ForeignKey(OperationRecord, null=True, blank=True, on_delete=models.SET_NULL, related_name="schedule_requests")
    fleet = models.ForeignKey(FleetRecord, null=True, blank=True, on_delete=models.SET_NULL, related_name="schedule_requests")
    payload = models.JSONField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    persisted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["workspace", "status", "not_before", "created_at"]
        indexes = [
            models.Index(fields=["workspace", "status", "not_before"]),
            models.Index(fields=["workspace", "target_type", "target_id", "status"]),
        ]


class RetentionPolicyRecord(models.Model):
    policy_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="retention_policies")
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="retention_policies")
    enabled = models.BooleanField(default=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workspace", "policy_id"]


class PackSignatureRecord(models.Model):
    signature_id = models.CharField(max_length=255, unique=True)
    pack = models.ForeignKey(KnowledgePackRecord, on_delete=models.CASCADE, related_name="signatures")
    scheme = models.CharField(max_length=64)
    key_id = models.CharField(max_length=255)
    signer = models.CharField(max_length=255)
    signature = models.TextField()
    manifest_hash = models.CharField(max_length=64)
    signed_at = models.DateTimeField()
    payload = models.JSONField()

    class Meta:
        ordering = ["pack", "-signed_at"]
        indexes = [models.Index(fields=["pack", "key_id", "signed_at"])]


class PackTrustPolicyRecord(models.Model):
    policy_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="pack_trust_policies")
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="pack_trust_policies")
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workspace", "policy_id"]


class SecretReferenceRecord(models.Model):
    secret_ref_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="secret_references")
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="secret_references")
    provider = models.CharField(max_length=64)
    locator_redacted = models.CharField(max_length=512)
    purpose = models.TextField(blank=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workspace", "secret_ref_id"]


class PlatformBackupRecord(models.Model):
    backup_id = models.CharField(max_length=255, unique=True)
    organization = models.ForeignKey(OrganizationRecord, on_delete=models.CASCADE, related_name="platform_backups")
    workspace = models.ForeignKey(WorkspaceRecord, on_delete=models.CASCADE, related_name="platform_backups")
    status = models.CharField(max_length=32)
    manifest_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField()
    payload = models.JSONField()
    persisted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "status", "created_at"])]
