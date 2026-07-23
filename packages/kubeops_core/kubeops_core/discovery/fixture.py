from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import yaml

from kubeops_core.models.enums import HealthStatus
from kubeops_core.models.environment import AccessCheck, AccessValidationResult, EnvironmentDefinition
from kubeops_core.util import utc_now_iso

from .sanitize import sanitize_resource
from .source import RawCollection


class FixtureDiscoverySource:
    source_id = "fixture"

    @staticmethod
    def _path(environment: EnvironmentDefinition, method_id: str | None) -> Path:
        method = environment.access_method(method_id)
        if method.method_type != "fixture" or not method.fixture_path:
            raise ValueError("selected access method is not a fixture method")
        return Path(method.fixture_path).expanduser().resolve()

    @staticmethod
    def _load(path: Path) -> dict:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            return json.loads(text)
        return yaml.safe_load(text)

    def validate(self, environment: EnvironmentDefinition, method_id: str | None = None) -> AccessValidationResult:
        method = environment.access_method(method_id)
        path = self._path(environment, method_id)
        exists = path.exists()
        parseable = False
        message = f"fixture {path} does not exist"
        if exists:
            try:
                payload = self._load(path)
                parseable = isinstance(payload, dict) and isinstance(payload.get("resources"), dict)
                message = "fixture is readable and contains a resources mapping" if parseable else "fixture lacks a resources mapping"
            except Exception as exc:  # noqa: BLE001 - surfaced as validation evidence
                message = f"fixture could not be parsed: {exc}"
        status = HealthStatus.HEALTHY if parseable else HealthStatus.UNHEALTHY
        return AccessValidationResult(
            validation_id=f"access-validation:{uuid4()}",
            environment_id=environment.environment_id,
            access_method_id=method.method_id,
            checked_at_iso=utc_now_iso(),
            status=status,
            target_fingerprint=f"fixture:{path}",
            capabilities={"fixture_replay"} if parseable else set(),
            checks=[
                AccessCheck(
                    check_id="fixture.readable",
                    title="Fixture is readable",
                    status=status,
                    explanation=message,
                    details={"path": str(path), "exists": exists},
                )
            ],
        )

    def collect(
        self,
        environment: EnvironmentDefinition,
        method_id: str | None = None,
        resource_types: list[str] | None = None,
    ) -> RawCollection:
        path = self._path(environment, method_id)
        payload = self._load(path)
        raw_resources = payload.get("resources", {})
        selected = set(resource_types or raw_resources.keys())
        resources: dict[str, list[dict]] = {}
        for resource_type, items in raw_resources.items():
            if resource_type not in selected:
                continue
            if isinstance(items, dict) and "items" in items:
                items = items["items"]
            if not isinstance(items, list):
                continue
            resources[resource_type] = [sanitize_resource(item) for item in items if isinstance(item, dict)]
        return RawCollection(
            source_type="fixture",
            source_fingerprint=str(payload.get("source_fingerprint") or f"fixture:{path}"),
            resources=resources,
            issues=list(payload.get("issues", [])),
            permission_gaps=list(payload.get("permission_gaps", [])),
            metadata={
                "fixture_path": str(path),
                "fixture_metadata": payload.get("metadata", {}),
            },
        )
