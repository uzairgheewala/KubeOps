from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from kubeops_core.models import OperationalEntity, Relationship
from kubeops_core.models.discovery import ResourceDocument
from kubeops_core.models.enums import OperationalPlane
from kubeops_core.models.pack import (
    EntityClassifierRule,
    KnowledgePackManifest,
    PackCoverageReport,
    PackResolution,
    RedactionRule,
    RelationshipResolverRule,
)
from kubeops_core.util import get_path, utc_now_iso




def _entity_types(entity: OperationalEntity) -> set[str]:
    return {entity.entity_type, *entity.entity_type_lineage}


def _kubernetes(entity: OperationalEntity) -> dict[str, Any]:
    value = entity.extensions.get("kubernetes", {})
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class PackRuntime:
    resolution: PackResolution
    manifests: tuple[KnowledgePackManifest, ...]

    @property
    def active_pack_ids(self) -> list[str]:
        return list(self.resolution.active_pack_ids)

    def _contributions(self, field: str) -> list[Any]:
        result: list[Any] = []
        for manifest in self.manifests:
            for item in getattr(manifest.contributions, field):
                if hasattr(item, "metadata"):
                    item = item.model_copy(update={"metadata": {**item.metadata, "pack_id": manifest.pack_id, "pack_version": manifest.version}})
                result.append(item)
        return result

    def entity_classifiers(self) -> list[EntityClassifierRule]:
        return sorted(self._contributions("entity_classifiers"), key=lambda item: (-item.priority, item.classifier_id))

    def relationship_resolvers(self) -> list[RelationshipResolverRule]:
        return self._contributions("relationship_resolvers")

    def operational_profiles(self):
        return self._contributions("operational_profiles")

    def evidence_intents(self):
        return self._contributions("evidence_intents")

    def collectors(self):
        return self._contributions("collectors")

    def causal_templates(self):
        return self._contributions("causal_templates")

    def action_types(self):
        return self._contributions("action_types")

    def lifecycle_profiles(self):
        return self._contributions("lifecycle_profiles")

    def verification_templates(self):
        return self._contributions("verification_templates")

    def redaction_rules(self) -> list[RedactionRule]:
        return self._contributions("redaction_rules")

    def classify_entity(self, document: ResourceDocument, entity: OperationalEntity) -> OperationalEntity:
        payload = document.payload
        metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
        labels = metadata.get("labels", {}) if isinstance(metadata.get("labels"), dict) else {}
        annotations = metadata.get("annotations", {}) if isinstance(metadata.get("annotations"), dict) else {}
        updates: dict[str, Any] = {}
        type_lineage = set(entity.entity_type_lineage) | {entity.entity_type}
        capabilities = set(entity.capabilities)
        extensions = dict(entity.extensions)
        matched: list[str] = []
        for rule in self.entity_classifiers():
            if rule.resource_kinds and document.resource_kind not in rule.resource_kinds:
                continue
            if rule.namespaces and (document.namespace or "") not in rule.namespaces:
                continue
            if rule.name_regex and re.search(rule.name_regex, document.name) is None:
                continue
            if any(labels.get(key) != value for key, value in rule.label_equals.items()):
                continue
            if any(annotations.get(key) != value for key, value in rule.annotation_equals.items()):
                continue
            matched.append(rule.classifier_id)
            if rule.set_entity_type:
                type_lineage.add(rule.set_entity_type)
                updates["entity_type"] = rule.set_entity_type
            if rule.set_plane:
                updates["plane"] = OperationalPlane(rule.set_plane)
            if rule.set_provider:
                updates["provider"] = rule.set_provider
            capabilities.update(rule.add_capabilities)
            if rule.extension_namespace:
                current = extensions.get(rule.extension_namespace, {})
                current = current if isinstance(current, dict) else {}
                extensions[rule.extension_namespace] = {**current, **rule.extension_values}
        if not matched:
            return entity
        pack_metadata = extensions.get("kubeops_pack", {})
        pack_metadata = pack_metadata if isinstance(pack_metadata, dict) else {}
        extensions["kubeops_pack"] = {**pack_metadata, "classifiers": matched}
        return entity.model_copy(update={**updates, "entity_type_lineage": type_lineage, "capabilities": capabilities, "extensions": extensions})

    def resolve_relationships(self, entities: Iterable[OperationalEntity]) -> list[Relationship]:
        entity_list = list(entities)
        by_id = {item.entity_id: item for item in entity_list}
        by_type: dict[str, list[OperationalEntity]] = defaultdict(list)
        by_kind_ns_name: dict[tuple[str, str | None, str], OperationalEntity] = {}
        for entity in entity_list:
            by_type[entity.entity_type].append(entity)
            kind = str(_kubernetes(entity).get("kind", ""))
            by_kind_ns_name[(kind, entity.namespace, entity.name)] = entity

        result: dict[str, Relationship] = {}
        for rule in self.relationship_resolvers():
            sources = entity_list if not rule.source_entity_types else [
                item for item in entity_list if _entity_types(item) & rule.source_entity_types
            ]
            if rule.handler_id == "annotation_reference":
                if not rule.annotation_key:
                    continue
                for source in sources:
                    resource = _kubernetes(source).get("sanitized_resource", {})
                    metadata = resource.get("metadata", {}) if isinstance(resource, dict) else {}
                    annotations = metadata.get("annotations", {}) if isinstance(metadata, dict) else {}
                    raw_target = annotations.get(rule.annotation_key) if isinstance(annotations, dict) else None
                    if not raw_target:
                        continue
                    target = by_id.get(str(raw_target))
                    if target is None and rule.target_kind:
                        namespace, _, name = str(raw_target).rpartition("/")
                        target = by_kind_ns_name.get((rule.target_kind, namespace or source.namespace, name or str(raw_target)))
                    if target:
                        self._add_relationship(result, rule, source, target)
            elif rule.handler_id == "label_group":
                if not rule.label_key:
                    continue
                targets = entity_list if not rule.target_entity_types else [
                    item for item in entity_list if _entity_types(item) & rule.target_entity_types
                ]
                for source in sources:
                    value = source.labels.get(rule.label_key)
                    if not value:
                        continue
                    for target in targets:
                        if source.entity_id != target.entity_id and target.labels.get(rule.label_key) == value:
                            self._add_relationship(result, rule, source, target)
            elif rule.handler_id == "named_kubernetes_resource":
                if not rule.target_kind or not rule.target_name:
                    continue
                for source in sources:
                    target = by_kind_ns_name.get((rule.target_kind, rule.target_namespace or source.namespace, rule.target_name))
                    if target:
                        self._add_relationship(result, rule, source, target)
            elif rule.handler_id == "component_dependency":
                for source in sources:
                    dependencies = source.extensions.get("dependencies", [])
                    if not isinstance(dependencies, list):
                        continue
                    for target_id in dependencies:
                        target = by_id.get(str(target_id))
                        if target:
                            self._add_relationship(result, rule, source, target)
        return sorted(result.values(), key=lambda item: item.relationship_id)

    @staticmethod
    def _add_relationship(result: dict[str, Relationship], rule: RelationshipResolverRule, source: OperationalEntity, target: OperationalEntity) -> None:
        relationship = Relationship(
            relationship_id=f"pack:{rule.resolver_id}:{source.entity_id}->{target.entity_id}",
            source_id=source.entity_id,
            target_id=target.entity_id,
            relationship_type=rule.relationship_type,
            confidence=rule.confidence,
            provenance=f"pack:{rule.resolver_id}",
            contract=rule.contract,
            propagation=rule.propagation,
            extensions={"resolver_id": rule.resolver_id},
        )
        result[relationship.relationship_id] = relationship

    def redact(self, payload: Any, *, resource_kind: str | None = None) -> Any:
        rules = [
            rule for rule in self.redaction_rules()
            if not rule.applies_to_resource_kinds or resource_kind in rule.applies_to_resource_kinds
        ]
        if not rules:
            return payload

        def visit(value: Any, path: str = "") -> Any:
            if isinstance(value, dict):
                result: dict[str, Any] = {}
                for key, child in value.items():
                    child_path = f"{path}.{key}" if path else str(key)
                    matched = next((rule for rule in rules if any(re.search(pattern, str(key), re.I) for pattern in rule.key_patterns) or any(re.search(pattern, child_path) for pattern in rule.path_patterns)), None)
                    result[key] = matched.replacement if matched else visit(child, child_path)
                return result
            if isinstance(value, list):
                return [visit(item, f"{path}[]") for item in value]
            return value

        return visit(payload)

    def coverage_report(self) -> PackCoverageReport:
        by_pack = {manifest.pack_id: manifest.contributions.scenario_coverage for manifest in self.manifests}
        family_support: dict[str, list[dict[str, Any]]] = defaultdict(list)
        invariant_support: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for manifest in self.manifests:
            for coverage in manifest.contributions.scenario_coverage:
                record = {"pack_id": manifest.pack_id, "support_level": coverage.support_level}
                for family_id in coverage.family_ids:
                    family_support[family_id].append(record)
                for family in coverage.invariant_families:
                    invariant_support[family].append(record)
        return PackCoverageReport(
            generated_at_iso=utc_now_iso(),
            active_pack_ids=self.active_pack_ids,
            by_pack=by_pack,
            family_support=dict(sorted(family_support.items())),
            invariant_support=dict(sorted(invariant_support.items())),
            gaps=[],
        )

    def contribution_counts(self) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for manifest in self.manifests:
            counter.update(manifest.contributions.counts())
        return dict(sorted(counter.items()))
