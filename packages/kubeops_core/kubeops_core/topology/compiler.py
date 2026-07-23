from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable
from uuid import uuid4

from kubeops_core.models.discovery import DiscoveryBundle, EnvironmentSnapshot
from kubeops_core.models.entity import OperationalEntity
from kubeops_core.models.relationship import Relationship
from kubeops_core.models.topology import TopologyGraph
from kubeops_core.util import get_path, utc_now_iso


def _k8s(entity: OperationalEntity) -> dict[str, Any]:
    value = entity.extensions.get("kubernetes", {})
    return value if isinstance(value, dict) else {}


def _resource(entity: OperationalEntity) -> dict[str, Any]:
    value = _k8s(entity).get("sanitized_resource", {})
    return value if isinstance(value, dict) else {}


def _kind(entity: OperationalEntity) -> str:
    return str(_k8s(entity).get("kind", ""))


def _relationship(
    source: OperationalEntity,
    target: OperationalEntity,
    relationship_type: str,
    provenance: str,
    *,
    confidence: float = 1.0,
    contract: dict[str, Any] | None = None,
) -> Relationship:
    return Relationship(
        relationship_id=f"{relationship_type}:{source.entity_id}->{target.entity_id}",
        source_id=source.entity_id,
        target_id=target.entity_id,
        relationship_type=relationship_type,
        confidence=confidence,
        provenance=provenance,
        contract=contract or {},
    )


class TopologyCompiler:
    """Compile Kubernetes object references into a typed operational graph."""

    def compile_bundle(self, bundle: DiscoveryBundle) -> TopologyGraph:
        return self._compile(
            environment_id=bundle.environment_id,
            snapshot_id=bundle.bundle_id,
            entities=bundle.entities,
            base_relationships=bundle.relationships,
        )

    def compile_snapshot(self, snapshot: EnvironmentSnapshot) -> TopologyGraph:
        return self._compile(
            environment_id=snapshot.environment_id,
            snapshot_id=snapshot.snapshot_id,
            entities=snapshot.entities,
            base_relationships=snapshot.relationships,
        )

    def _compile(
        self,
        *,
        environment_id: str,
        snapshot_id: str,
        entities: list[OperationalEntity],
        base_relationships: list[Relationship],
    ) -> TopologyGraph:
        by_kind: dict[str, list[OperationalEntity]] = defaultdict(list)
        by_kind_ns_name: dict[tuple[str, str | None, str], OperationalEntity] = {}
        by_uid: dict[str, OperationalEntity] = {}
        for entity in entities:
            kind = _kind(entity)
            by_kind[kind].append(entity)
            by_kind_ns_name[(kind, entity.namespace, entity.name)] = entity
            uid = _k8s(entity).get("uid")
            if uid:
                by_uid[str(uid)] = entity

        relationships: dict[str, Relationship] = {item.relationship_id: item for item in base_relationships}

        def add(item: Relationship | None) -> None:
            if item is not None:
                relationships[item.relationship_id] = item

        self._compile_workload_pod_control(by_kind, by_uid, relationships)
        self._compile_pod_dependencies(by_kind, by_kind_ns_name, add)
        self._compile_services(by_kind, add)
        self._compile_endpoint_slices(by_kind, by_kind_ns_name, by_uid, add)
        self._compile_ingresses(by_kind, by_kind_ns_name, add)
        self._compile_storage(by_kind, by_kind_ns_name, add)
        self._compile_rbac(by_kind, by_kind_ns_name, add)

        rels = sorted(relationships.values(), key=lambda item: item.relationship_id)
        layers: dict[str, list[str]] = defaultdict(list)
        for entity in entities:
            layers[str(entity.plane)].append(entity.entity_id)
        kinds = Counter(_kind(entity) or entity.entity_type for entity in entities)
        rel_types = Counter(item.relationship_type for item in rels)
        warnings = self._warnings(entities, rels)
        return TopologyGraph(
            graph_id=f"topology:{uuid4()}",
            environment_id=environment_id,
            snapshot_id=snapshot_id,
            generated_at_iso=utc_now_iso(),
            entities=sorted(entities, key=lambda item: item.entity_id),
            relationships=rels,
            layers={key: sorted(value) for key, value in layers.items()},
            statistics={
                "entity_count": len(entities),
                "relationship_count": len(rels),
                "entity_kinds": dict(sorted(kinds.items())),
                "relationship_types": dict(sorted(rel_types.items())),
                "namespace_count": len({entity.namespace for entity in entities if entity.namespace}),
                "warning_count": len(warnings),
            },
            warnings=warnings,
        )

    @staticmethod
    def _compile_workload_pod_control(
        by_kind: dict[str, list[OperationalEntity]],
        by_uid: dict[str, OperationalEntity],
        relationships: dict[str, Relationship],
    ) -> None:
        for child in [*by_kind.get("Pod", []), *by_kind.get("ReplicaSet", [])]:
            for owner in _k8s(child).get("owner_references", []) or []:
                parent = by_uid.get(str(owner.get("uid", "")))
                if parent is None:
                    continue
                rel = _relationship(parent, child, "controls", "kubernetes.ownerReferences", contract={"controller": bool(owner.get("controller"))})
                relationships[rel.relationship_id] = rel

    @staticmethod
    def _compile_pod_dependencies(
        by_kind: dict[str, list[OperationalEntity]],
        by_key: dict[tuple[str, str | None, str], OperationalEntity],
        add: Any,
    ) -> None:
        for pod in by_kind.get("Pod", []):
            resource = _resource(pod)
            namespace = pod.namespace
            node_name = get_path(resource, "spec.nodeName", None)
            if node_name:
                node = by_key.get(("Node", None, str(node_name)))
                if node:
                    add(_relationship(pod, node, "scheduled_on", "pod.spec.nodeName"))
            service_account = get_path(resource, "spec.serviceAccountName", "default")
            account = by_key.get(("ServiceAccount", namespace, str(service_account)))
            if account:
                add(_relationship(pod, account, "uses_identity", "pod.spec.serviceAccountName"))

            refs: set[tuple[str, str]] = set()
            for volume in get_path(resource, "spec.volumes", []) or []:
                if not isinstance(volume, dict):
                    continue
                if isinstance(volume.get("configMap"), dict) and volume["configMap"].get("name"):
                    refs.add(("ConfigMap", str(volume["configMap"]["name"])))
                if isinstance(volume.get("secret"), dict) and volume["secret"].get("secretName"):
                    refs.add(("Secret", str(volume["secret"]["secretName"])))
                if isinstance(volume.get("persistentVolumeClaim"), dict) and volume["persistentVolumeClaim"].get("claimName"):
                    refs.add(("PersistentVolumeClaim", str(volume["persistentVolumeClaim"]["claimName"])))
                projected = volume.get("projected") if isinstance(volume.get("projected"), dict) else {}
                for source in projected.get("sources", []) or []:
                    if isinstance(source, dict) and isinstance(source.get("secret"), dict) and source["secret"].get("name"):
                        refs.add(("Secret", str(source["secret"]["name"])))
                    if isinstance(source, dict) and isinstance(source.get("configMap"), dict) and source["configMap"].get("name"):
                        refs.add(("ConfigMap", str(source["configMap"]["name"])))
            containers = [*(get_path(resource, "spec.initContainers", []) or []), *(get_path(resource, "spec.containers", []) or [])]
            for container in containers:
                if not isinstance(container, dict):
                    continue
                for env_from in container.get("envFrom", []) or []:
                    if not isinstance(env_from, dict):
                        continue
                    if isinstance(env_from.get("secretRef"), dict) and env_from["secretRef"].get("name"):
                        refs.add(("Secret", str(env_from["secretRef"]["name"])))
                    if isinstance(env_from.get("configMapRef"), dict) and env_from["configMapRef"].get("name"):
                        refs.add(("ConfigMap", str(env_from["configMapRef"]["name"])))
                for env in container.get("env", []) or []:
                    value_from = env.get("valueFrom", {}) if isinstance(env, dict) else {}
                    if isinstance(value_from.get("secretKeyRef"), dict) and value_from["secretKeyRef"].get("name"):
                        refs.add(("Secret", str(value_from["secretKeyRef"]["name"])))
                    if isinstance(value_from.get("configMapKeyRef"), dict) and value_from["configMapKeyRef"].get("name"):
                        refs.add(("ConfigMap", str(value_from["configMapKeyRef"]["name"])))
            for kind, name in refs:
                target = by_key.get((kind, namespace, name))
                if target:
                    relationship_type = {
                        "Secret": "references_secret",
                        "ConfigMap": "references_config",
                        "PersistentVolumeClaim": "mounts_claim",
                    }[kind]
                    add(_relationship(pod, target, relationship_type, "pod.spec"))

    @staticmethod
    def _compile_services(by_kind: dict[str, list[OperationalEntity]], add: Any) -> None:
        pods = by_kind.get("Pod", [])
        for service in by_kind.get("Service", []):
            selector = get_path(_resource(service), "spec.selector", {})
            if not isinstance(selector, dict) or not selector:
                continue
            for pod in pods:
                if pod.namespace != service.namespace:
                    continue
                if all(pod.labels.get(key) == value for key, value in selector.items()):
                    add(_relationship(service, pod, "selects", "service.spec.selector", contract={"selector": selector}))

    @staticmethod
    def _compile_endpoint_slices(
        by_kind: dict[str, list[OperationalEntity]],
        by_key: dict[tuple[str, str | None, str], OperationalEntity],
        by_uid: dict[str, OperationalEntity],
        add: Any,
    ) -> None:
        for endpoint_slice in by_kind.get("EndpointSlice", []):
            resource = _resource(endpoint_slice)
            service_name = endpoint_slice.labels.get("kubernetes.io/service-name")
            if service_name:
                service = by_key.get(("Service", endpoint_slice.namespace, str(service_name)))
                if service:
                    add(_relationship(service, endpoint_slice, "publishes_endpoints", "endpointslice.label"))
            for endpoint in get_path(resource, "endpoints", []) or []:
                if not isinstance(endpoint, dict):
                    continue
                ref = endpoint.get("targetRef") if isinstance(endpoint.get("targetRef"), dict) else {}
                target = by_uid.get(str(ref.get("uid", ""))) or by_key.get((str(ref.get("kind", "Pod")), endpoint_slice.namespace, str(ref.get("name", ""))))
                if target:
                    ready = get_path(endpoint, "conditions.ready", None)
                    add(_relationship(endpoint_slice, target, "routes_to", "endpointslice.endpoints", contract={"ready": ready}))

    @staticmethod
    def _compile_ingresses(
        by_kind: dict[str, list[OperationalEntity]],
        by_key: dict[tuple[str, str | None, str], OperationalEntity],
        add: Any,
    ) -> None:
        for ingress in by_kind.get("Ingress", []):
            resource = _resource(ingress)
            backends: list[dict[str, Any]] = []
            default_backend = get_path(resource, "spec.defaultBackend", None)
            if isinstance(default_backend, dict):
                backends.append(default_backend)
            for rule in get_path(resource, "spec.rules", []) or []:
                for path in get_path(rule, "http.paths", []) or []:
                    if isinstance(path, dict) and isinstance(path.get("backend"), dict):
                        backends.append(path["backend"])
            for backend in backends:
                service_name = get_path(backend, "service.name", None)
                if not service_name:
                    continue
                service = by_key.get(("Service", ingress.namespace, str(service_name)))
                if service:
                    add(_relationship(ingress, service, "routes_to", "ingress.spec", contract={"backend": backend}))

    @staticmethod
    def _compile_storage(
        by_kind: dict[str, list[OperationalEntity]],
        by_key: dict[tuple[str, str | None, str], OperationalEntity],
        add: Any,
    ) -> None:
        for pvc in by_kind.get("PersistentVolumeClaim", []):
            resource = _resource(pvc)
            volume_name = get_path(resource, "spec.volumeName", None)
            if volume_name:
                pv = by_key.get(("PersistentVolume", None, str(volume_name)))
                if pv:
                    add(_relationship(pvc, pv, "binds_to", "pvc.spec.volumeName"))
            storage_class = get_path(resource, "spec.storageClassName", None)
            if storage_class:
                sc = by_key.get(("StorageClass", None, str(storage_class)))
                if sc:
                    add(_relationship(pvc, sc, "uses_storage_class", "pvc.spec.storageClassName"))

    @staticmethod
    def _compile_rbac(
        by_kind: dict[str, list[OperationalEntity]],
        by_key: dict[tuple[str, str | None, str], OperationalEntity],
        add: Any,
    ) -> None:
        for binding_kind in ["RoleBinding", "ClusterRoleBinding"]:
            for binding in by_kind.get(binding_kind, []):
                resource = _resource(binding)
                role_ref = get_path(resource, "roleRef", {})
                if isinstance(role_ref, dict):
                    role_kind = str(role_ref.get("kind", "Role"))
                    role_namespace = None if role_kind == "ClusterRole" else binding.namespace
                    role = by_key.get((role_kind, role_namespace, str(role_ref.get("name", ""))))
                    if role:
                        add(_relationship(binding, role, "grants_role", "rolebinding.roleRef"))
                for subject in get_path(resource, "subjects", []) or []:
                    if not isinstance(subject, dict):
                        continue
                    subject_kind = str(subject.get("kind", ""))
                    namespace = subject.get("namespace") if subject_kind == "ServiceAccount" else None
                    target = by_key.get((subject_kind, namespace, str(subject.get("name", ""))))
                    if target:
                        add(_relationship(binding, target, "binds_subject", "rolebinding.subjects"))

    @staticmethod
    def _warnings(entities: list[OperationalEntity], relationships: list[Relationship]) -> list[str]:
        outgoing: dict[str, list[Relationship]] = defaultdict(list)
        for relationship in relationships:
            outgoing[relationship.source_id].append(relationship)
        warnings: list[str] = []
        for entity in entities:
            kind = _kind(entity)
            if kind == "Service" and get_path(_resource(entity), "spec.selector", {}) and not any(rel.relationship_type in {"selects", "publishes_endpoints"} for rel in outgoing[entity.entity_id]):
                warnings.append(f"Service {entity.namespace}/{entity.name} has a selector but no discovered backing relationship")
            if kind == "Ingress" and not any(rel.relationship_type == "routes_to" for rel in outgoing[entity.entity_id]):
                warnings.append(f"Ingress {entity.namespace}/{entity.name} has no discovered Service backend")
        return warnings
