from __future__ import annotations

import hashlib
import json
import os
import subprocess
from uuid import uuid4

from kubeops_core.models.enums import HealthStatus
from kubeops_core.models.environment import (
    AccessCheck,
    AccessValidationResult,
    EnvironmentDefinition,
    PermissionGap,
)
from kubeops_core.util import utc_now_iso

from .sanitize import sanitize_resource
from .source import RawCollection


DEFAULT_RESOURCE_TYPES = [
    "namespaces",
    "nodes",
    "deployments.apps",
    "statefulsets.apps",
    "daemonsets.apps",
    "replicasets.apps",
    "jobs.batch",
    "cronjobs.batch",
    "pods",
    "services",
    "endpointslices.discovery.k8s.io",
    "ingresses.networking.k8s.io",
    "configmaps",
    "secrets",
    "serviceaccounts",
    "roles.rbac.authorization.k8s.io",
    "rolebindings.rbac.authorization.k8s.io",
    "clusterroles.rbac.authorization.k8s.io",
    "clusterrolebindings.rbac.authorization.k8s.io",
    "persistentvolumes",
    "persistentvolumeclaims",
    "storageclasses.storage.k8s.io",
    "customresourcedefinitions.apiextensions.k8s.io",
    "events",
]


class KubectlCommandError(RuntimeError):
    def __init__(self, args: list[str], returncode: int, stdout: str, stderr: str) -> None:
        super().__init__(f"kubectl command failed ({returncode}): {' '.join(args)}: {stderr.strip()}")
        self.args_list = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class KubectlDiscoverySource:
    source_id = "kubectl"

    def _base(self, environment: EnvironmentDefinition, method_id: str | None) -> tuple[list[str], dict[str, str], int, str]:
        method = environment.access_method(method_id)
        if method.method_type not in {"kubectl", "kubeconfig"}:
            raise ValueError("selected access method is not kubectl-compatible")
        args = [method.command]
        env = os.environ.copy()
        if method.kubeconfig_path:
            args += ["--kubeconfig", method.kubeconfig_path]
        if method.context_name:
            args += ["--context", method.context_name]
        return args, env, method.timeout_seconds, method.method_id

    def _run(
        self,
        environment: EnvironmentDefinition,
        args: list[str],
        method_id: str | None = None,
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        base, env, timeout, _ = self._base(environment, method_id)
        process = subprocess.run(
            [*base, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        if check and process.returncode != 0:
            raise KubectlCommandError([*base, *args], process.returncode, process.stdout, process.stderr)
        return process

    def _json(self, environment: EnvironmentDefinition, args: list[str], method_id: str | None = None) -> dict:
        process = self._run(environment, args, method_id)
        return json.loads(process.stdout)

    def validate(self, environment: EnvironmentDefinition, method_id: str | None = None) -> AccessValidationResult:
        method = environment.access_method(method_id)
        checks: list[AccessCheck] = []
        permissions: list[PermissionGap] = []
        capabilities: set[str] = set()
        current_context: str | None = None
        server: str | None = None
        version: str | None = None
        fingerprint_parts = [environment.environment_id, method.method_id]

        context_process = self._run(environment, ["config", "current-context"], method_id, check=False)
        if context_process.returncode == 0:
            current_context = context_process.stdout.strip()
            checks.append(AccessCheck(check_id="kubectl.context", title="Kubernetes context resolves", status=HealthStatus.HEALTHY, explanation=f"current context is {current_context}"))
            fingerprint_parts.append(current_context)
        else:
            checks.append(AccessCheck(check_id="kubectl.context", title="Kubernetes context resolves", status=HealthStatus.UNHEALTHY, explanation=context_process.stderr.strip() or "current context unavailable"))

        version_process = self._run(environment, ["version", "-o", "json"], method_id, check=False)
        if version_process.returncode == 0:
            payload = json.loads(version_process.stdout)
            server_info = payload.get("serverVersion", {})
            version = server_info.get("gitVersion")
            checks.append(AccessCheck(check_id="kubernetes.api", title="Kubernetes API is reachable", status=HealthStatus.HEALTHY, explanation=f"server version {version or 'unknown'}", details=payload))
            capabilities.add("kubernetes_api_read")
            fingerprint_parts.append(str(version))
        else:
            checks.append(AccessCheck(check_id="kubernetes.api", title="Kubernetes API is reachable", status=HealthStatus.UNHEALTHY, explanation=version_process.stderr.strip() or "kubectl version failed"))

        view_process = self._run(environment, ["config", "view", "--minify", "-o", "json"], method_id, check=False)
        if view_process.returncode == 0:
            config = json.loads(view_process.stdout)
            clusters = config.get("clusters", [])
            if clusters:
                server = clusters[0].get("cluster", {}).get("server")
                if server:
                    fingerprint_parts.append(server)

        for resource in ["namespaces", "nodes", "pods", "services", "deployments.apps"]:
            process = self._run(environment, ["auth", "can-i", "list", resource, "--all-namespaces"], method_id, check=False)
            permitted = process.returncode == 0 and process.stdout.strip().lower() == "yes"
            checks.append(
                AccessCheck(
                    check_id=f"permission.list.{resource}",
                    title=f"Can list {resource}",
                    status=HealthStatus.HEALTHY if permitted else HealthStatus.DEGRADED,
                    explanation=process.stdout.strip() or process.stderr.strip() or "permission unknown",
                )
            )
            if not permitted:
                permissions.append(PermissionGap(resource=resource, required_for=["snapshot", "topology", "health"]))

        if any(check.status == HealthStatus.UNHEALTHY for check in checks):
            status = HealthStatus.UNHEALTHY
        elif permissions:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY
        fingerprint = hashlib.sha256("|".join(fingerprint_parts).encode()).hexdigest()
        return AccessValidationResult(
            validation_id=f"access-validation:{uuid4()}",
            environment_id=environment.environment_id,
            access_method_id=method.method_id,
            checked_at_iso=utc_now_iso(),
            status=status,
            target_fingerprint=fingerprint,
            current_context=current_context,
            cluster_server=server,
            cluster_version=version,
            capabilities=capabilities,
            checks=checks,
            permission_gaps=permissions,
        )

    def collect(
        self,
        environment: EnvironmentDefinition,
        method_id: str | None = None,
        resource_types: list[str] | None = None,
    ) -> RawCollection:
        validation = self.validate(environment, method_id)
        resources: dict[str, list[dict]] = {}
        issues: list[dict] = []
        permission_gaps = [item.model_dump(mode="json") for item in validation.permission_gaps]
        for resource_type in resource_types or DEFAULT_RESOURCE_TYPES:
            process = self._run(
                environment,
                ["get", resource_type, "--all-namespaces", "--ignore-not-found", "-o", "json"],
                method_id,
                check=False,
            )
            if process.returncode != 0:
                lower = process.stderr.lower()
                if "forbidden" in lower or "cannot list" in lower:
                    permission_gaps.append({"resource": resource_type, "verb": "list", "scope": "cluster", "reason": process.stderr.strip(), "required_for": ["snapshot"]})
                else:
                    issues.append({"severity": "warning", "collector_id": self.source_id, "resource_type": resource_type, "message": process.stderr.strip() or "collection failed"})
                continue
            payload = json.loads(process.stdout or "{}")
            items = payload.get("items", [])
            resources[resource_type] = [sanitize_resource(item) for item in items if isinstance(item, dict)]
        status = "complete" if not issues and not permission_gaps else "partial"
        return RawCollection(
            source_type="live",
            source_fingerprint=validation.target_fingerprint,
            resources=resources,
            issues=issues,
            permission_gaps=permission_gaps,
            metadata={
                "validation": validation.model_dump(mode="json"),
                "collection_status": status,
            },
        )
