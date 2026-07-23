from __future__ import annotations

from django.db import models


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
        indexes = [models.Index(fields=["family_id", "created_at"])]


class EnvironmentRecord(models.Model):
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
        indexes = [models.Index(fields=["scope_type", "scope_id"])]


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
