from __future__ import annotations

import re
from typing import Any, Iterable

from kubeops_core.models.discovery import ResourceDocument
from kubeops_core.models.entity import OperationalEntity
from kubeops_core.models.enums import OperationalPlane
from kubeops_core.models.observation import Observation
from kubeops_core.models.relationship import Relationship
from kubeops_core.util import get_path


WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob"}
CONTROL_PLANE_NAMES = {"kube-apiserver", "kube-scheduler", "kube-controller-manager", "etcd"}
PLATFORM_NAMES = {"coredns", "kube-proxy", "ingress-nginx", "argocd", "metrics-server"}


def canonical_resource_id(kind: str, namespace: str | None, name: str) -> str:
    scope = namespace or "_cluster"
    return f"k8s/{kind.lower()}/{scope}/{name}"


def _conditions(status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for condition in status.get("conditions", []) or []:
        if not isinstance(condition, dict) or not condition.get("type"):
            continue
        normalized = dict(condition)
        raw_status = normalized.get("status")
        if raw_status in {"True", "False"}:
            normalized["status"] = raw_status == "True"
        result[str(condition["type"])] = normalized
    return result


def _pod_ready(status: dict[str, Any]) -> bool | None:
    ready = _conditions(status).get("Ready", {}).get("status")
    return ready if isinstance(ready, bool) else None


def _plane(kind: str, name: str, namespace: str | None) -> OperationalPlane:
    if kind in {"Node"}:
        return OperationalPlane.NODE
    if kind in {"Namespace", "CustomResourceDefinition", "StorageClass", "ClusterRole", "ClusterRoleBinding", "PersistentVolume"}:
        return OperationalPlane.CONTROL_PLANE
    lowered = name.lower()
    if any(token in lowered for token in CONTROL_PLANE_NAMES):
        return OperationalPlane.CONTROL_PLANE
    if namespace in {"kube-system", "argocd", "ingress-nginx", "cert-manager", "monitoring"} or any(token in lowered for token in PLATFORM_NAMES):
        return OperationalPlane.PLATFORM
    if kind in WORKLOAD_KINDS | {"Pod", "Service", "EndpointSlice", "Ingress", "PersistentVolumeClaim", "ConfigMap", "Secret", "ServiceAccount", "Role", "RoleBinding"}:
        return OperationalPlane.WORKLOAD
    return OperationalPlane.APPLICATION


def _desired_state(resource: dict[str, Any]) -> dict[str, Any]:
    spec = resource.get("spec") if isinstance(resource.get("spec"), dict) else {}
    desired: dict[str, Any] = {"exists": True}
    for key in ["replicas", "selector", "serviceName", "type", "storageClassName", "accessModes", "volumeName", "suspend", "parallelism", "completions"]:
        if key in spec:
            desired[key] = spec[key]
    return desired


def _observed_state(resource: dict[str, Any]) -> dict[str, Any]:
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
    status = resource.get("status") if isinstance(resource.get("status"), dict) else {}
    kind = str(resource.get("kind", "Unknown"))
    observed: dict[str, Any] = {
        "exists": True,
        "generation": metadata.get("generation"),
        "resource_version": metadata.get("resourceVersion"),
        "deleting": bool(metadata.get("deletionTimestamp")),
        "conditions": _conditions(status),
    }
    for key in [
        "phase",
        "observedGeneration",
        "replicas",
        "readyReplicas",
        "availableReplicas",
        "updatedReplicas",
        "currentReplicas",
        "succeeded",
        "failed",
        "active",
        "numberReady",
        "numberAvailable",
        "desiredNumberScheduled",
        "currentNumberScheduled",
        "capacity",
        "allocatable",
        "podIP",
        "hostIP",
    ]:
        if key in status:
            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()
            observed[snake] = status[key]
    if kind == "Pod":
        observed["ready"] = _pod_ready(status)
        container_statuses = status.get("containerStatuses", []) or []
        observed["restart_count"] = sum(int(item.get("restartCount", 0)) for item in container_statuses if isinstance(item, dict))
        observed["container_states"] = [item.get("state", {}) for item in container_statuses if isinstance(item, dict)]
    if kind == "Node":
        observed["ready"] = _conditions(status).get("Ready", {}).get("status")
    if kind in WORKLOAD_KINDS:
        desired_replicas = get_path(resource, "spec.replicas", 1)
        observed["desired_replicas"] = desired_replicas
        observed["ready_replicas"] = observed.get("ready_replicas", 0)
    if kind == "PersistentVolumeClaim":
        observed["bound"] = status.get("phase") == "Bound"
    return observed


def resource_document(resource: dict[str, Any], source: str, observed_at_iso: str) -> ResourceDocument:
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
    kind = str(resource.get("kind", "Unknown"))
    name = str(metadata.get("name", "unknown"))
    namespace = metadata.get("namespace")
    return ResourceDocument(
        resource_id=canonical_resource_id(kind, namespace, name),
        api_version=str(resource.get("apiVersion", "unknown")),
        resource_kind=kind,
        name=name,
        namespace=namespace,
        payload=resource,
        source=source,
        observed_at_iso=observed_at_iso,
    )


def normalize_entity(document: ResourceDocument) -> OperationalEntity:
    resource = document.payload
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
    annotations = metadata.get("annotations") if isinstance(metadata.get("annotations"), dict) else {}
    owner_refs = metadata.get("ownerReferences") if isinstance(metadata.get("ownerReferences"), list) else []
    return OperationalEntity(
        entity_id=document.resource_id,
        entity_type=f"kubernetes.{document.resource_kind.lower()}",
        name=document.name,
        plane=_plane(document.resource_kind, document.name, document.namespace),
        namespace=document.namespace,
        provider="kubernetes",
        labels=metadata.get("labels", {}) if isinstance(metadata.get("labels"), dict) else {},
        desired_state=_desired_state(resource),
        observed_state=_observed_state(resource),
        capabilities={"observable", "kubernetes_resource"},
        extensions={
            "kubernetes": {
                "api_version": document.api_version,
                "kind": document.resource_kind,
                "uid": metadata.get("uid"),
                "generation": metadata.get("generation"),
                "resource_version": metadata.get("resourceVersion"),
                "creation_timestamp": metadata.get("creationTimestamp"),
                "owner_references": owner_refs,
                "annotations": annotations,
                "sanitized_resource": resource,
            }
        },
    )


def normalize_observation(entity: OperationalEntity, observed_at_iso: str, source: str) -> Observation:
    return Observation(
        observation_id=f"observation:{entity.content_hash[:24]}",
        entity_id=entity.entity_id,
        observed_at_iso=observed_at_iso,
        state=entity.model_dump(mode="json"),
        source=source,
        authority="kubernetes_api" if source != "fixture" else "recorded_fixture",
        freshness_seconds=0,
        profile_id="live" if source != "fixture" else "fixture",
    )


def owner_relationships(entities: Iterable[OperationalEntity]) -> list[Relationship]:
    entities_list = list(entities)
    by_uid: dict[str, OperationalEntity] = {}
    by_scope_kind_name: dict[tuple[str | None, str, str], OperationalEntity] = {}
    for entity in entities_list:
        k8s = entity.extensions.get("kubernetes", {})
        uid = k8s.get("uid")
        if uid:
            by_uid[str(uid)] = entity
        by_scope_kind_name[(entity.namespace, str(k8s.get("kind", "")), entity.name)] = entity

    result: list[Relationship] = []
    for child in entities_list:
        k8s = child.extensions.get("kubernetes", {})
        for owner in k8s.get("owner_references", []) or []:
            if not isinstance(owner, dict):
                continue
            parent = by_uid.get(str(owner.get("uid", ""))) or by_scope_kind_name.get((child.namespace, str(owner.get("kind", "")), str(owner.get("name", ""))))
            if parent is None:
                continue
            result.append(
                Relationship(
                    relationship_id=f"owner:{child.entity_id}->{parent.entity_id}",
                    source_id=child.entity_id,
                    target_id=parent.entity_id,
                    relationship_type="owned_by",
                    confidence=1.0,
                    provenance="kubernetes.ownerReferences",
                    contract={"controller": bool(owner.get("controller"))},
                )
            )
    return result
