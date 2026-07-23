import pytest
from django.test import Client, override_settings

from api.services import clear_service_caches


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def configure_paths(repo_root, tmp_path):
    with override_settings(
        KUBEOPS_SCENARIO_DIR=repo_root / "scenarios",
        KUBEOPS_ARTIFACT_DIR=tmp_path / "artifacts",
    ):
        clear_service_caches()
        yield
        clear_service_caches()


def test_status_and_family_endpoints(db) -> None:
    client = Client()
    status_response = client.get("/api/v1/system/status")
    assert status_response.status_code == 200
    assert status_response.json()["mode"] == "simulation"

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
