from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from .base import SchemaModel


class BackupComponent(SchemaModel):
    kind: ClassVar[str] = "BackupComponent"

    component_id: str
    component_type: str
    source: str
    payload_hash: str
    size_bytes: int = Field(default=0, ge=0)
    required_for_restore: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ControlPlaneBackupManifest(SchemaModel):
    kind: ClassVar[str] = "ControlPlaneBackupManifest"

    backup_id: str
    organization_id: str
    workspace_id: str
    created_at_iso: str
    kubeops_version: str
    schema_version: str
    components: list[BackupComponent]
    pack_resolution_hash: str | None = None
    audit_head_hash: str | None = None
    database_vendor: str = "unknown"
    status: Literal["created", "verified", "invalid"] = "created"
    manifest_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RestoreStep(SchemaModel):
    kind: ClassVar[str] = "RestoreStep"

    step_id: str
    title: str
    order: int = Field(ge=0)
    component_ids: list[str]
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    manual: bool = False


class ControlPlaneRestorePlan(SchemaModel):
    kind: ClassVar[str] = "ControlPlaneRestorePlan"

    plan_id: str
    backup_id: str
    generated_at_iso: str
    target_kubeops_version: str
    compatible: bool
    steps: list[RestoreStep]
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpgradeReadinessCheck(SchemaModel):
    kind: ClassVar[str] = "UpgradeReadinessCheck"

    check_id: str
    status: Literal["pass", "warn", "fail", "unknown"]
    title: str
    explanation: str
    details: dict[str, Any] = Field(default_factory=dict)


class UpgradeReadinessReport(SchemaModel):
    kind: ClassVar[str] = "UpgradeReadinessReport"

    report_id: str
    current_version: str
    target_version: str
    generated_at_iso: str
    ready: bool
    checks: list[UpgradeReadinessCheck]
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
