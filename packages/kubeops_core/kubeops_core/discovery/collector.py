from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from kubeops_core.models.discovery import DiscoveryBundle, DiscoveryIssue
from kubeops_core.models.environment import EnvironmentDefinition
from kubeops_core.util import utc_now_iso

from .normalize import normalize_entity, normalize_observation, owner_relationships, resource_document
from .source import DiscoverySource


@dataclass(frozen=True)
class DiscoveryRequest:
    method_id: str | None = None
    resource_types: list[str] | None = None


class DiscoveryCollector:
    def __init__(self, source: DiscoverySource) -> None:
        self.source = source

    def collect(self, environment: EnvironmentDefinition, request: DiscoveryRequest | None = None) -> DiscoveryBundle:
        request = request or DiscoveryRequest()
        started = utc_now_iso()
        raw = self.source.collect(environment, request.method_id, request.resource_types)
        completed = utc_now_iso()
        documents = []
        for resource_type in sorted(raw.resources):
            for item in raw.resources[resource_type]:
                documents.append(resource_document(item, self.source.source_id, completed))
        entities = [normalize_entity(document) for document in documents]
        relationships = owner_relationships(entities)
        observations = [normalize_observation(entity, completed, self.source.source_id) for entity in entities]
        issues = [
            DiscoveryIssue(
                issue_id=f"discovery-issue:{index}:{uuid4()}",
                severity=item.get("severity", "warning"),
                collector_id=item.get("collector_id", self.source.source_id),
                resource_type=item.get("resource_type"),
                message=item.get("message", "unspecified discovery issue"),
                details=item.get("details", {}),
            )
            for index, item in enumerate(raw.issues)
        ]
        status = "complete" if not issues and not raw.permission_gaps else "partial"
        return DiscoveryBundle(
            bundle_id=f"discovery-bundle:{uuid4()}",
            environment_id=environment.environment_id,
            collector_id=self.source.source_id,
            source_type=raw.source_type,  # type: ignore[arg-type]
            started_at_iso=started,
            completed_at_iso=completed,
            status=status,
            source_fingerprint=raw.source_fingerprint,
            resources=documents,
            entities=entities,
            relationships=relationships,
            observations=observations,
            issues=issues,
            permission_gaps=raw.permission_gaps,
            collection_summary={
                "resource_document_count": len(documents),
                "entity_count": len(entities),
                "base_relationship_count": len(relationships),
                "observation_count": len(observations),
                "resource_types": {key: len(value) for key, value in raw.resources.items()},
                "issue_count": len(issues),
                "permission_gap_count": len(raw.permission_gaps),
            },
            metadata=raw.metadata,
        )
