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


class ArtifactRecord(models.Model):
    artifact_id = models.CharField(max_length=255, unique=True)
    run = models.ForeignKey(ScenarioRunRecord, on_delete=models.CASCADE, related_name="artifacts")
    artifact_type = models.CharField(max_length=64)
    content_hash = models.CharField(max_length=64)
    media_type = models.CharField(max_length=128)
    storage_path = models.TextField()
    derived_from = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


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
