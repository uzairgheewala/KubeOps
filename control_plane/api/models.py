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
