from __future__ import annotations

from typing import Any

from kubeops_core.models.discovery import DiscoveryBundle


def export_discovery_fixture(
    bundle: DiscoveryBundle,
    *,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Convert an internal sanitized discovery bundle into the public replay format.

    The bundle has already crossed the mandatory sanitization boundary. This
    function intentionally exports only the sanitized resource payloads and
    collection evidence required by ``FixtureDiscoverySource``.
    """

    resources: dict[str, list[dict[str, Any]]] = {}
    for document in bundle.resources:
        resources.setdefault(document.resource_kind, []).append(document.payload)

    metadata = dict(bundle.metadata)
    metadata["exported_from_bundle_id"] = bundle.bundle_id
    if snapshot_id is not None:
        metadata["exported_from_snapshot_id"] = snapshot_id

    return {
        "api_version": "kubeops.io/discovery-fixture/v1",
        "source_fingerprint": bundle.source_fingerprint,
        "metadata": metadata,
        "resources": resources,
        "issues": [item.model_dump(mode="json") for item in bundle.issues],
        "permission_gaps": bundle.permission_gaps,
    }
