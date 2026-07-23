from __future__ import annotations

from typing import Any
from uuid import uuid4

from kubeops_core.models.discovery import (
    DiscoveryBundle,
    EntityChange,
    EnvironmentSnapshot,
    FieldChange,
    RelationshipChange,
    SnapshotDiff,
)
from kubeops_core.models.entity import OperationalEntity
from kubeops_core.models.relationship import Relationship
from kubeops_core.models.topology import TopologyGraph
from kubeops_core.util import utc_now_iso


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(child, path))
        return result
    return {prefix: value}


class SnapshotBuilder:
    def build(self, bundle: DiscoveryBundle, topology: TopologyGraph) -> EnvironmentSnapshot:
        return EnvironmentSnapshot(
            snapshot_id=f"snapshot:{uuid4()}",
            environment_id=bundle.environment_id,
            captured_at_iso=bundle.completed_at_iso,
            started_at_iso=bundle.started_at_iso,
            completed_at_iso=bundle.completed_at_iso,
            status=bundle.status,
            source_type=bundle.source_type,
            source_fingerprint=bundle.source_fingerprint,
            entities=topology.entities,
            relationships=topology.relationships,
            observations=bundle.observations,
            issues=bundle.issues,
            permission_gaps=bundle.permission_gaps,
            raw_resource_count=len(bundle.resources),
            collection_summary={
                **bundle.collection_summary,
                "compiled_relationship_count": len(topology.relationships),
                "topology_warning_count": len(topology.warnings),
            },
            metadata={
                **bundle.metadata,
                "bundle_id": bundle.bundle_id,
                "topology_graph_id": topology.graph_id,
                "topology_warnings": topology.warnings,
            },
        )


def _entity_change(before: OperationalEntity | None, after: OperationalEntity | None) -> EntityChange:
    entity_id = (after or before).entity_id  # type: ignore[union-attr]
    if before is None:
        return EntityChange(entity_id=entity_id, change_type="added", after_hash=after.content_hash if after else None)
    if after is None:
        return EntityChange(entity_id=entity_id, change_type="removed", before_hash=before.content_hash)
    before_flat = _flatten(before.model_dump(mode="json", exclude={"schema_version"}))
    after_flat = _flatten(after.model_dump(mode="json", exclude={"schema_version"}))
    changes = [
        FieldChange(path=path, before=before_flat.get(path), after=after_flat.get(path))
        for path in sorted(set(before_flat) | set(after_flat))
        if before_flat.get(path) != after_flat.get(path)
    ]
    return EntityChange(
        entity_id=entity_id,
        change_type="changed",
        before_hash=before.content_hash,
        after_hash=after.content_hash,
        field_changes=changes,
    )


def _relationship_change(before: Relationship | None, after: Relationship | None) -> RelationshipChange:
    relationship_id = (after or before).relationship_id  # type: ignore[union-attr]
    if before is None:
        return RelationshipChange(relationship_id=relationship_id, change_type="added", after_hash=after.content_hash if after else None)
    if after is None:
        return RelationshipChange(relationship_id=relationship_id, change_type="removed", before_hash=before.content_hash)
    return RelationshipChange(relationship_id=relationship_id, change_type="changed", before_hash=before.content_hash, after_hash=after.content_hash)


def diff_snapshots(before: EnvironmentSnapshot, after: EnvironmentSnapshot) -> SnapshotDiff:
    if before.environment_id != after.environment_id:
        raise ValueError("snapshots belong to different environments")
    before_entities = {item.entity_id: item for item in before.entities}
    after_entities = {item.entity_id: item for item in after.entities}
    entity_changes: list[EntityChange] = []
    for entity_id in sorted(set(before_entities) | set(after_entities)):
        old = before_entities.get(entity_id)
        new = after_entities.get(entity_id)
        if old is None or new is None or old.content_hash != new.content_hash:
            entity_changes.append(_entity_change(old, new))

    before_rels = {item.relationship_id: item for item in before.relationships}
    after_rels = {item.relationship_id: item for item in after.relationships}
    relationship_changes: list[RelationshipChange] = []
    for relationship_id in sorted(set(before_rels) | set(after_rels)):
        old = before_rels.get(relationship_id)
        new = after_rels.get(relationship_id)
        if old is None or new is None or old.content_hash != new.content_hash:
            relationship_changes.append(_relationship_change(old, new))

    summary = {
        "entities_added": sum(item.change_type == "added" for item in entity_changes),
        "entities_removed": sum(item.change_type == "removed" for item in entity_changes),
        "entities_changed": sum(item.change_type == "changed" for item in entity_changes),
        "relationships_added": sum(item.change_type == "added" for item in relationship_changes),
        "relationships_removed": sum(item.change_type == "removed" for item in relationship_changes),
        "relationships_changed": sum(item.change_type == "changed" for item in relationship_changes),
    }
    return SnapshotDiff(
        diff_id=f"snapshot-diff:{uuid4()}",
        environment_id=before.environment_id,
        before_snapshot_id=before.snapshot_id,
        after_snapshot_id=after.snapshot_id,
        created_at_iso=utc_now_iso(),
        entity_changes=entity_changes,
        relationship_changes=relationship_changes,
        summary=summary,
    )
