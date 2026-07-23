from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.http import JsonResponse

from .audit import append_audit_event
from .models import OrganizationRecord, WorkspaceRecord


class AuditMiddleware:
    """Create a tamper-evident start and outcome record for every API mutation.

    In production the request is rejected before execution if the audit chain
    cannot accept its start record. The start record remains useful even when
    an external side effect prevents a final outcome record from being written.
    """

    def __init__(self, get_response):  # type: ignore[no-untyped-def]
        self.get_response = get_response

    def __call__(self, request):  # type: ignore[no-untyped-def]
        is_mutation = request.path.startswith("/api/v1/") and request.method not in {
            "GET",
            "HEAD",
            "OPTIONS",
        }
        if not is_mutation:
            return self.get_response(request)

        request_id = request.headers.get("X-Request-Id") or f"request:{uuid4()}"
        scope = self._scope(request)
        if scope is not None:
            organization, workspace = scope
            try:
                append_audit_event(
                    organization=organization,
                    workspace=workspace,
                    principal_id=self._principal(request),
                    action=f"{request.method}:{request.path}",
                    resource_type="api_request",
                    resource_id=request.path,
                    outcome="started",
                    details={"phase": "request_started"},
                    request_id=request_id,
                    source_ip=request.META.get("REMOTE_ADDR"),
                    user_agent=request.headers.get("User-Agent"),
                )
            except Exception as exc:  # noqa: BLE001 - fail-closed policy is explicit
                if settings.KUBEOPS_AUDIT_REQUIRED:
                    return JsonResponse(
                        {
                            "detail": "audit chain unavailable; mutating request was not executed",
                            "error_type": type(exc).__name__,
                            "request_id": request_id,
                        },
                        status=503,
                    )

        response = self.get_response(request)
        response["X-Request-Id"] = request_id
        if scope is not None:
            organization, workspace = scope
            try:
                append_audit_event(
                    organization=organization,
                    workspace=workspace,
                    principal_id=self._principal(request),
                    action=f"{request.method}:{request.path}",
                    resource_type="api_request",
                    resource_id=request.path,
                    outcome="success" if response.status_code < 400 else "failure",
                    details={"phase": "request_completed", "status_code": response.status_code},
                    request_id=request_id,
                    source_ip=request.META.get("REMOTE_ADDR"),
                    user_agent=request.headers.get("User-Agent"),
                )
            except Exception:
                # The preflight event guarantees the attempted mutation is still
                # represented even if completion logging encounters a later fault.
                response["X-KubeOps-Audit-Completion"] = "failed"
        return response

    @staticmethod
    def _principal(request) -> str:  # type: ignore[no-untyped-def]
        user = getattr(request, "user", None)
        return str(user.pk) if getattr(user, "is_authenticated", False) else "anonymous"

    @staticmethod
    def _scope(request):  # type: ignore[no-untyped-def]
        organization_id = request.headers.get(
            "X-KubeOps-Organization", settings.KUBEOPS_DEFAULT_ORGANIZATION_ID
        )
        workspace_id = request.headers.get(
            "X-KubeOps-Workspace", settings.KUBEOPS_DEFAULT_WORKSPACE_ID
        )
        organization = OrganizationRecord.objects.filter(
            organization_id=organization_id
        ).first()
        workspace = WorkspaceRecord.objects.filter(
            workspace_id=workspace_id,
            organization=organization,
        ).first()
        if organization is None or workspace is None:
            return None
        return organization, workspace
