from __future__ import annotations

from django.conf import settings
from rest_framework.exceptions import PermissionDenied


def requested_scope(request) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    return (
        request.headers.get("X-KubeOps-Organization", settings.KUBEOPS_DEFAULT_ORGANIZATION_ID),
        request.headers.get("X-KubeOps-Workspace", settings.KUBEOPS_DEFAULT_WORKSPACE_ID),
    )


def enforce_payload_scope(
    request,  # type: ignore[no-untyped-def]
    *,
    organization_id: str,
    workspace_id: str,
) -> None:
    """Reject cross-scope writes unless the authenticated principal is superuser."""

    if getattr(request.user, "is_superuser", False):
        return
    requested_organization, requested_workspace = requested_scope(request)
    if organization_id != requested_organization or workspace_id != requested_workspace:
        raise PermissionDenied("payload organization/workspace does not match the authorized request scope")
