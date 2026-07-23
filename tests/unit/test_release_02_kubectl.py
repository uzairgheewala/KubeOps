from __future__ import annotations

import json
import subprocess

from kubeops_core.discovery import DiscoveryCollector, DiscoveryRequest, KubectlDiscoverySource
from kubeops_core.models import AccessMethodDefinition, EnvironmentDefinition


def kubectl_environment() -> EnvironmentDefinition:
    return EnvironmentDefinition(
        environment_id="live-kind",
        name="Live Kind",
        environment_class="development",
        provider="local",
        cluster_provider="kind",
        access_methods=[
            AccessMethodDefinition(
                method_id="observer",
                method_type="kubectl",
                context_name="kind-test",
                command="kubectl",
            )
        ],
        default_access_method_id="observer",
    )


def test_kubectl_validation_is_read_only_and_fingerprints_target(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        suffix = args[args.index("kind-test") + 1 :] if "kind-test" in args else args[1:]
        if suffix == ["config", "current-context"]:
            return subprocess.CompletedProcess(args, 0, "kind-test\n", "")
        if suffix == ["version", "-o", "json"]:
            return subprocess.CompletedProcess(args, 0, json.dumps({"serverVersion": {"gitVersion": "v1.31.2"}}), "")
        if suffix == ["config", "view", "--minify", "-o", "json"]:
            payload = {"clusters": [{"cluster": {"server": "https://127.0.0.1:6443"}}]}
            return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")
        if suffix[:3] == ["auth", "can-i", "list"]:
            return subprocess.CompletedProcess(args, 0, "yes\n", "")
        raise AssertionError(f"unexpected kubectl call: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = KubectlDiscoverySource().validate(kubectl_environment())

    assert result.status == "healthy"
    assert result.current_context == "kind-test"
    assert result.cluster_server == "https://127.0.0.1:6443"
    assert result.cluster_version == "v1.31.2"
    assert result.target_fingerprint
    assert all(command[0] == "kubectl" for command in calls)
    assert not any(any(token in command for token in ["apply", "patch", "delete", "create"]) for command in calls)


def test_kubectl_collection_sanitizes_secrets_before_bundle(monkeypatch) -> None:
    def fake_run(args, **kwargs):
        suffix = args[args.index("kind-test") + 1 :] if "kind-test" in args else args[1:]
        if suffix == ["config", "current-context"]:
            return subprocess.CompletedProcess(args, 0, "kind-test\n", "")
        if suffix == ["version", "-o", "json"]:
            return subprocess.CompletedProcess(args, 0, json.dumps({"serverVersion": {"gitVersion": "v1.31.2"}}), "")
        if suffix == ["config", "view", "--minify", "-o", "json"]:
            return subprocess.CompletedProcess(args, 0, json.dumps({"clusters": [{"cluster": {"server": "https://127.0.0.1:6443"}}]}), "")
        if suffix[:3] == ["auth", "can-i", "list"]:
            return subprocess.CompletedProcess(args, 0, "yes\n", "")
        if suffix[:2] == ["get", "pods"]:
            pod = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": "web", "namespace": "demo", "uid": "pod-1"},
                "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]},
            }
            return subprocess.CompletedProcess(args, 0, json.dumps({"items": [pod]}), "")
        if suffix[:2] == ["get", "secrets"]:
            secret = {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": "database", "namespace": "demo", "uid": "secret-1"},
                "data": {"PASSWORD": "c3VwZXItc2VjcmV0"},
            }
            return subprocess.CompletedProcess(args, 0, json.dumps({"items": [secret]}), "")
        raise AssertionError(f"unexpected kubectl call: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)
    bundle = DiscoveryCollector(KubectlDiscoverySource()).collect(
        kubectl_environment(),
        DiscoveryRequest(resource_types=["pods", "secrets"]),
    )

    assert bundle.status == "complete"
    assert bundle.source_type == "live"
    assert len(bundle.resources) == 2
    secret = next(item for item in bundle.resources if item.resource_kind == "Secret")
    assert "data" not in secret.payload
    assert secret.payload["redaction"]["data_keys"] == ["PASSWORD"]
    assert "c3VwZXItc2VjcmV0" not in bundle.model_dump_json()
