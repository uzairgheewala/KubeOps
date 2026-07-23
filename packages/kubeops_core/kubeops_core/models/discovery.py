from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from .base import SchemaModel
from .entity import OperationalEntity
from .observation import Observation
from .relationship import Relationship


CollectionStatus = Literal["complete", "partial", "failed"]


class DiscoveryIssue(SchemaModel):
    kind: ClassVar[str] = "DiscoveryIssue"

    issue_id: str
    severity: Literal["info", "warning", "error"] = "warning"
    collector_id: str
    resource_type: str | None = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ResourceDocument(SchemaModel):
    """A sanitized API object retained for replay and pack-specific interpretation."""

    kind: ClassVar[str] = "ResourceDocument"

    resource_id: str
    api_version: str
    resource_kind: str
    name: str
    namespace: str | None = None
    payload: dict[str, Any]
    source: str
    observed_at_iso: str
    content_hash_hint: str | None = None


class DiscoveryBundle(SchemaModel):
    kind: ClassVar[str] = "DiscoveryBundle"

    bundle_id: str
    environment_id: str
    collector_id: str
    source_type: Literal["live", "fixture"]
    started_at_iso: str
    completed_at_iso: str
    status: CollectionStatus
    source_fingerprint: str
    resources: list[ResourceDocument] = Field(default_factory=list)
    entities: list[OperationalEntity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    issues: list[DiscoveryIssue] = Field(default_factory=list)
    permission_gaps: list[dict[str, Any]] = Field(default_factory=list)
    collection_summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnvironmentSnapshot(SchemaModel):
    kind: ClassVar[str] = "EnvironmentSnapshot"

    snapshot_id: str
    environment_id: str
    captured_at_iso: str
    started_at_iso: str
    completed_at_iso: str
    status: CollectionStatus
    source_type: Literal["live", "fixture"]
    source_fingerprint: str
    entities: list[OperationalEntity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    issues: list[DiscoveryIssue] = Field(default_factory=list)
    permission_gaps: list[dict[str, Any]] = Field(default_factory=list)
    raw_resource_count: int = Field(default=0, ge=0)
    collection_summary: dict[str, Any] = Field(default_factory=dict)
    raw_artifact_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FieldChange(SchemaModel):
    kind: ClassVar[str] = "FieldChange"

    path: str
    before: Any = None
    after: Any = None


class EntityChange(SchemaModel):
    kind: ClassVar[str] = "EntityChange"

    entity_id: str
    change_type: Literal["added", "removed", "changed"]
    before_hash: str | None = None
    after_hash: str | None = None
    field_changes: list[FieldChange] = Field(default_factory=list)


class RelationshipChange(SchemaModel):
    kind: ClassVar[str] = "RelationshipChange"

    relationship_id: str
    change_type: Literal["added", "removed", "changed"]
    before_hash: str | None = None
    after_hash: str | None = None


class SnapshotDiff(SchemaModel):
    kind: ClassVar[str] = "SnapshotDiff"

    diff_id: str
    environment_id: str
    before_snapshot_id: str
    after_snapshot_id: str
    created_at_iso: str
    entity_changes: list[EntityChange] = Field(default_factory=list)
    relationship_changes: list[RelationshipChange] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
