from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.test import Client, override_settings

from api.services import clear_service_caches


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def configure_paths(repo_root: Path, tmp_path: Path):
    with override_settings(
        KUBEOPS_SCENARIO_DIR=repo_root / "scenarios",
        KUBEOPS_PROFILE_DIR=repo_root / "profiles",
        KUBEOPS_ARTIFACT_DIR=tmp_path / "artifacts",
        KUBEOPS_LIFECYCLE_DIR=repo_root / "lifecycle",
        KUBEOPS_POLICY_DIR=repo_root / "policies",
        KUBEOPS_OPERATION_DIR=tmp_path / "operations",
        KUBEOPS_PACK_DIR=repo_root / "packs",
        KUBEOPS_ENABLED_PACKS=[],
        KUBEOPS_LIVE_EXECUTION_ENABLED=False,
    ):
        clear_service_caches()
        yield
        clear_service_caches()


def test_status_profiles_and_family_endpoints(db) -> None:
    client = Client()
    status_response = client.get("/api/v1/system/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["mode"] == "guarded_lifecycle_recovery"
    assert status_payload["release"] == "0.5.0"
    assert status_payload["profile_count"] >= 2
    assert "immutable_snapshots" in status_payload["capabilities"]
    assert "probe_planning" in status_payload["capabilities"]
    assert status_payload["diagnostic_collector_count"] >= 10
    assert status_payload["action_type_count"] >= 10
    assert status_payload["lifecycle_profile_count"] >= 2
    assert "durable_execution" in status_payload["capabilities"]
    assert status_payload["pack_count"] == 11
    assert status_payload["active_pack_count"] == 11
    assert "knowledge_packs" in status_payload["capabilities"]

    catalog_response = client.get("/api/v1/diagnostic-catalog")
    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    assert catalog["read_only"] is True
    assert catalog["counts"]["intents"] >= 8
    assert catalog["counts"]["collectors"] >= 10
    assert catalog["counts"]["causal_templates"] >= 10

    profiles_response = client.get("/api/v1/operational-profiles")
    assert profiles_response.status_code == 200
    assert {item["profile_id"] for item in profiles_response.json()} >= {
        "cluster-observable.v1",
        "local-development-usable.v1",
    }

    families_response = client.get("/api/v1/scenario-families")
    assert families_response.status_code == 200
    family = next(
        item
        for item in families_response.json()
        if item["family_id"] == "dependency.endpoint_unreachable.v1"
    )
    assert {parameter["name"] for parameter in family["parameters"]} >= {
        "consumer_id",
        "provider_id",
        "failure_layer",
    }


def test_fixture_environment_snapshot_health_diff_and_export(db, repo_root: Path) -> None:
    client = Client()
    fixture_path = repo_root / "lab" / "fixtures" / "kind-demo-degraded.v1.yaml"
    environment = {
        "environment_id": "integration-kind",
        "name": "Integration Kind",
        "environment_class": "development",
        "provider": "fixture",
        "cluster_provider": "kind",
        "access_methods": [
            {
                "method_id": "fixture",
                "method_type": "fixture",
                "title": "Recorded fixture",
                "fixture_path": str(fixture_path),
            }
        ],
        "default_access_method_id": "fixture",
        "operational_profile_ids": [
            "cluster-observable.v1",
            "local-development-usable.v1",
        ],
    }
    create_response = client.post("/api/v1/environments", data=environment, content_type="application/json")
    assert create_response.status_code == 201

    validation_response = client.post(
        "/api/v1/environments/integration-kind/validate",
        data={},
        content_type="application/json",
    )
    assert validation_response.status_code == 201
    assert validation_response.json()["status"] == "healthy"

    first_response = client.post(
        "/api/v1/environments/integration-kind/snapshots",
        data={},
        content_type="application/json",
    )
    assert first_response.status_code == 201
    first = first_response.json()
    assert first["raw_resource_count"] >= 20
    assert len(first["topology"]["relationships"]) >= 25
    assessment_by_id = {item["profile_id"]: item for item in first["assessments"]}
    assert assessment_by_id["cluster-observable.v1"]["status"] == "healthy"
    assert assessment_by_id["local-development-usable.v1"]["status"] == "unhealthy"

    snapshot_id = first["snapshot_id"]
    incident_response = client.post(
        f"/api/v1/snapshots/{snapshot_id}/incidents",
        data={"profile_id": "local-development-usable.v1", "evidence_budget": 4},
        content_type="application/json",
    )
    assert incident_response.status_code == 201
    incident = incident_response.json()
    assert incident["violated_invariant_ids"]
    assert incident["evidence"]
    assert incident["hypotheses"]
    assert incident["certificate"]
    assert incident["artifacts"]

    incident_detail = client.get(f"/api/v1/incidents/{incident['incident_id']}")
    assert incident_detail.status_code == 200
    assert incident_detail.json()["incident_id"] == incident["incident_id"]

    if incident.get("probe_plan", {}).get("probes"):
        probe_id = incident["probe_plan"]["probes"][0]["probe_id"]
        probe_response = client.post(
            f"/api/v1/incidents/{incident['incident_id']}/probes/{probe_id}/run",
            data={"evidence_budget": 4},
            content_type="application/json",
        )
        assert probe_response.status_code == 201
        assert probe_response.json()["probe_runs"]

    export_response = client.get(f"/api/v1/snapshots/{snapshot_id}/export")
    assert export_response.status_code == 200
    exported = export_response.json()
    assert exported["api_version"] == "kubeops.io/discovery-fixture/v1"
    assert isinstance(exported["resources"], dict)
    serialized = json.dumps(exported)
    assert "super-secret-password" not in serialized
    assert "password" in serialized

    second_response = client.post(
        "/api/v1/environments/integration-kind/snapshots",
        data={},
        content_type="application/json",
    )
    assert second_response.status_code == 201
    second = second_response.json()
    assert second["diff_from_previous"]["summary"] == {
        "entities_added": 0,
        "entities_removed": 0,
        "entities_changed": 0,
        "relationships_added": 0,
        "relationships_removed": 0,
        "relationships_changed": 0,
    }

    diff_response = client.get(f"/api/v1/snapshots/{second['snapshot_id']}/diff?before={snapshot_id}")
    assert diff_response.status_code == 200
    assert not diff_response.json()["entity_changes"]


def test_compile_and_run_persist_artifacts(db) -> None:
    client = Client()
    payload = {
        "family_id": "dependency.authentication_failure.v1",
        "bindings": {"consumer_name": "Builder", "provider_name": "Kubernetes API"},
        "observation_profile_id": "full",
    }
    compile_response = client.post(
        "/api/v1/scenarios/compile",
        data=payload,
        content_type="application/json",
    )
    assert compile_response.status_code == 201
    assert compile_response.json()["family_id"] == payload["family_id"]

    run_response = client.post(
        "/api/v1/scenarios/run",
        data=payload,
        content_type="application/json",
    )
    assert run_response.status_code == 201
    body = run_response.json()
    assert body["status"] == "completed"
    assert body["artifacts"]

    detail_response = client.get(f"/api/v1/runs/{body['run_id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["final_summary"]["unhealthy_invariants"]

    diagnosis_response = client.post(
        "/api/v1/scenarios/diagnose",
        data={
            **payload,
            "expectation": {
                "expected_family_ids": ["dependency.authentication_failure"],
                "maximum_probe_count": 8,
            },
        },
        content_type="application/json",
    )
    assert diagnosis_response.status_code == 201
    diagnosis = diagnosis_response.json()
    assert diagnosis["passed"] is True
    assert "dependency.authentication_failure" in diagnosis["predicted_family_ids"]
    assert diagnosis["incident"]["certificate"]


def test_composition_and_artifact_endpoints(db) -> None:
    client = Client()
    payload = {
        "schema_version": "kubeops.io/v1",
        "composition_id": "api-composition",
        "title": "Concurrent failures",
        "operator": "concurrent",
        "components": [
            {
                "schema_version": "kubeops.io/v1",
                "alias": "network",
                "family_id": "dependency.endpoint_unreachable.v1",
                "bindings": {},
                "duration_hint_seconds": 6,
            },
            {
                "schema_version": "kubeops.io/v1",
                "alias": "controller",
                "family_id": "controller.convergence_failure.v1",
                "bindings": {},
                "duration_hint_seconds": 6,
            },
        ],
        "bridge_relationships": [],
    }
    response = client.post("/api/v1/compositions/run", data=payload, content_type="application/json")
    assert response.status_code == 201
    body = response.json()
    assert body["family_id"] == "composition.concurrent"
    artifact_id = body["artifacts"][0]["artifact_id"]
    artifact_response = client.get(f"/api/v1/artifacts/{artifact_id}")
    assert artifact_response.status_code == 200
    assert artifact_response.json()["content_hash"]


def test_lifecycle_plan_approval_dry_run_and_certificate(db, repo_root: Path) -> None:
    client = Client()
    fixture_path = repo_root / "lab" / "fixtures" / "kind-demo-degraded.v1.yaml"
    environment = {
        "environment_id": "operation-kind", "name": "Operation Kind", "environment_class": "development",
        "provider": "fixture", "cluster_provider": "kind",
        "access_methods": [{"method_id": "fixture", "method_type": "fixture", "title": "Recorded fixture", "fixture_path": str(fixture_path)}],
        "default_access_method_id": "fixture", "operational_profile_ids": ["local-development-usable.v1"],
    }
    assert client.post("/api/v1/environments", data=environment, content_type="application/json").status_code == 201
    snapshot_response = client.post("/api/v1/environments/operation-kind/snapshots", data={}, content_type="application/json")
    assert snapshot_response.status_code == 201
    snapshot_id = snapshot_response.json()["snapshot_id"]

    plan_response = client.post(
        f"/api/v1/snapshots/{snapshot_id}/lifecycle/plan",
        data={"lifecycle_profile_id": "local-development-startup.v1", "mode": "dry_run"},
        content_type="application/json",
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()
    assert len(plan["actions"]) == 2
    assert len(plan["verification_conditions"]) == 2
    assert plan["actions"][1]["depends_on_action_ids"] == [plan["actions"][0]["action_id"]]

    create_response = client.post(
        "/api/v1/operations",
        data={"snapshot_id": snapshot_id, "lifecycle_profile_id": "local-development-startup.v1", "mode": "dry_run"},
        content_type="application/json",
    )
    assert create_response.status_code == 201
    operation = create_response.json()
    operation_id = operation["operation_id"]
    assert operation["status"] == "created"

    # A separate operation proves the durable cancellation endpoint without
    # consuming the primary execution fixture.
    cancel_created = client.post(
        "/api/v1/operations",
        data={"snapshot_id": snapshot_id, "lifecycle_profile_id": "local-development-shutdown.v1", "mode": "dry_run"},
        content_type="application/json",
    ).json()
    cancel_response = client.post(
        f"/api/v1/operations/{cancel_created['operation_id']}/cancel",
        data={"reason": "integration cancellation"},
        content_type="application/json",
    )
    assert cancel_response.status_code == 201
    assert cancel_response.json()["status"] == "cancelled"

    pending_response = client.post(f"/api/v1/operations/{operation_id}/run", data={}, content_type="application/json")
    assert pending_response.status_code == 201
    assert pending_response.json()["status"] == "awaiting_approval"
    assert any(item["outcome"] == "approval_required" for item in pending_response.json()["policy_decisions"])

    approval_response = client.post(
        f"/api/v1/operations/{operation_id}/approvals",
        data={"approver_id": "integration-operator", "decision": "approve"},
        content_type="application/json",
    )
    assert approval_response.status_code == 201
    assert approval_response.json()["approvals"]

    run_response = client.post(f"/api/v1/operations/{operation_id}/run", data={}, content_type="application/json")
    assert run_response.status_code == 201
    finished = run_response.json()
    assert finished["status"] == "completed"
    assert len(finished["action_receipts"]) == 2
    assert {item["executor_id"] for item in finished["action_receipts"]} == {"dry_run"}
    assert finished["checkpoints"]
    assert finished["verification_results"]
    assert finished["recovery_certificate"]["status"] == "partially_recovered"
    assert finished["artifacts"]

    detail = client.get(f"/api/v1/operations/{operation_id}")
    assert detail.status_code == 200
    assert detail.json()["recovery_certificate"]["metadata"]["dry_run"] is True
    certificate = client.get(f"/api/v1/operations/{operation_id}/certificate")
    assert certificate.status_code == 200
    assert certificate.json()["operation_id"] == operation_id


def test_live_execution_is_disabled_by_default(db, repo_root: Path) -> None:
    client = Client()
    fixture_path = repo_root / "lab" / "fixtures" / "kind-demo-degraded.v1.yaml"
    environment = {
        "environment_id": "live-disabled", "name": "Live Disabled", "environment_class": "development",
        "provider": "fixture", "cluster_provider": "kind",
        "access_methods": [{"method_id": "fixture", "method_type": "fixture", "title": "fixture", "fixture_path": str(fixture_path)}],
        "default_access_method_id": "fixture",
    }
    client.post("/api/v1/environments", data=environment, content_type="application/json")
    snapshot = client.post("/api/v1/environments/live-disabled/snapshots", data={}, content_type="application/json").json()
    operation = client.post("/api/v1/operations", data={"snapshot_id": snapshot["snapshot_id"], "lifecycle_profile_id": "local-development-startup.v1", "mode": "guarded_execution"}, content_type="application/json").json()
    response = client.post(f"/api/v1/operations/{operation['operation_id']}/run", data={"execution_mode": "live"}, content_type="application/json")
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]


def test_release_04_catalog_seeder(db) -> None:
    from django.core.management import call_command
    from api.models import ExecutionPolicyRecord, LifecycleProfileRecord

    call_command("seed_release_04", verbosity=0)
    assert LifecycleProfileRecord.objects.count() >= 2
    assert ExecutionPolicyRecord.objects.count() >= 2
    assert LifecycleProfileRecord.objects.filter(profile_id="local-development-startup.v1").exists()
    assert ExecutionPolicyRecord.objects.filter(policy_id="local-development-guarded.v1").exists()


def test_release_05_pack_endpoints_and_seeder(db) -> None:
    from django.core.management import call_command
    from api.models import KnowledgePackRecord

    client = Client()
    response = client.get("/api/v1/packs")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["packs"]) == 11
    assert payload["resolution"]["blocked_pack_ids"] == []
    assert payload["resolution"]["contribution_counts"]["action_types"] == 12

    detail = client.get("/api/v1/packs/kind")
    assert detail.status_code == 200
    assert detail.json()["manifest"]["pack_kind"] == "provider"
    assert {item["pack_id"] for item in detail.json()["manifest"]["dependencies"]} == {"generic-kubernetes", "docker-host"}

    resolution = client.post("/api/v1/packs/resolve", data={"pack_ids": ["kind"]}, content_type="application/json")
    assert resolution.status_code == 200
    assert resolution.json()["active_pack_ids"] == ["generic-kubernetes", "docker-host", "kind"]

    coverage = client.get("/api/v1/packs/coverage")
    assert coverage.status_code == 200
    assert "kind.control_plane_unavailable" in coverage.json()["family_support"]

    call_command("seed_release_05", verbosity=0)
    assert KnowledgePackRecord.objects.count() == 11
    assert KnowledgePackRecord.objects.filter(pack_id="kind", state="active", enabled=True).exists()
