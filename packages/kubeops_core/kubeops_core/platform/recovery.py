from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from kubeops_core.models.platform import (
    BackupComponent,
    ControlPlaneBackupManifest,
    ControlPlaneRestorePlan,
    RestoreStep,
    UpgradeReadinessCheck,
    UpgradeReadinessReport,
)
from kubeops_core.packs.versioning import satisfies
from kubeops_core.util import utc_now_iso


class PlatformRecoveryService:
    def build_backup_manifest(
        self,
        *,
        organization_id: str,
        workspace_id: str,
        kubeops_version: str,
        schema_version: str,
        components: list[BackupComponent],
        pack_resolution_hash: str | None = None,
        audit_head_hash: str | None = None,
        database_vendor: str = "unknown",
    ) -> ControlPlaneBackupManifest:
        base = {
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "kubeops_version": kubeops_version,
            "schema_version": schema_version,
            "components": [item.canonical_dict() for item in components],
            "pack_resolution_hash": pack_resolution_hash,
            "audit_head_hash": audit_head_hash,
            "database_vendor": database_vendor,
        }
        manifest_hash = hashlib.sha256(json.dumps(base, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return ControlPlaneBackupManifest(
            backup_id=f"platform-backup:{uuid4()}", created_at_iso=utc_now_iso(), status="created",
            manifest_hash=manifest_hash, **base,
        )


    @staticmethod
    def calculate_manifest_hash(manifest: ControlPlaneBackupManifest) -> str:
        base = {
            "organization_id": manifest.organization_id,
            "workspace_id": manifest.workspace_id,
            "kubeops_version": manifest.kubeops_version,
            "schema_version": manifest.schema_version,
            "components": [item.canonical_dict() for item in manifest.components],
            "pack_resolution_hash": manifest.pack_resolution_hash,
            "audit_head_hash": manifest.audit_head_hash,
            "database_vendor": manifest.database_vendor,
        }
        return hashlib.sha256(
            json.dumps(base, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def verify_manifest(
        self,
        manifest: ControlPlaneBackupManifest,
        component_payloads: dict[str, bytes | str | Path],
    ) -> ControlPlaneBackupManifest:
        failures: list[str] = []
        if not manifest.components:
            failures.append("backup manifest contains no restorable components")
        if self.calculate_manifest_hash(manifest) != manifest.manifest_hash:
            failures.append("manifest hash mismatch")
        for component in manifest.components:
            payload = component_payloads.get(component.component_id)
            if payload is None:
                if component.required_for_restore:
                    failures.append(f"required component {component.component_id} is unavailable")
                continue
            if isinstance(payload, Path):
                digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            elif isinstance(payload, str):
                digest = hashlib.sha256(payload.encode()).hexdigest()
            else:
                digest = hashlib.sha256(payload).hexdigest()
            if digest != component.payload_hash:
                failures.append(f"component {component.component_id} hash mismatch")
            if component.metadata.get("external_backup_required") and not component.metadata.get("external_backup_verified"):
                failures.append(f"component {component.component_id} requires external backup verification")
        metadata = dict(manifest.metadata)
        metadata["verification_failures"] = failures
        metadata["verified_at_iso"] = utc_now_iso()
        return manifest.model_copy(update={"status": "invalid" if failures else "verified", "metadata": metadata})

    def restore_plan(self, manifest: ControlPlaneBackupManifest, *, target_version: str) -> ControlPlaneRestorePlan:
        major = int(manifest.kubeops_version.split(".")[0])
        compatible = manifest.status == "verified" and satisfies(
            target_version,
            f">={major}.0.0,<{major + 1}.0.0",
        )
        steps = [
            RestoreStep(step_id="restore.database", title="Restore relational control-plane state", order=0,
                        component_ids=[item.component_id for item in manifest.components if item.component_type == "database"],
                        postconditions=["database schema reachable"]),
            RestoreStep(step_id="restore.artifacts", title="Restore immutable artifact store", order=1,
                        component_ids=[item.component_id for item in manifest.components if item.component_type == "artifact_store"],
                        preconditions=["database restored"], postconditions=["artifact hashes verified"]),
            RestoreStep(step_id="restore.configuration", title="Restore policies, packs, fleets, and environment definitions", order=2,
                        component_ids=[item.component_id for item in manifest.components if item.component_type not in {"database", "artifact_store"}],
                        preconditions=["database restored"], postconditions=["catalog resolution succeeds"]),
            RestoreStep(step_id="restore.verify", title="Run platform semantic verification", order=3,
                        component_ids=[], preconditions=["all required components restored"],
                        postconditions=["audit chain valid", "pack trust valid", "executor registration available"]),
        ]
        blockers = [] if compatible else ["backup is not verified or target version is outside the supported major-version restore range"]
        return ControlPlaneRestorePlan(
            plan_id=f"platform-restore:{uuid4()}", backup_id=manifest.backup_id, generated_at_iso=utc_now_iso(),
            target_kubeops_version=target_version, compatible=compatible, steps=steps, blockers=blockers,
        )

    def upgrade_readiness(
        self,
        *,
        current_version: str,
        target_version: str,
        database_migrations_pending: int,
        unresolved_pack_issues: int,
        audit_chain_valid: bool,
        recent_verified_backup: bool,
        active_operations: int,
    ) -> UpgradeReadinessReport:
        checks = [
            UpgradeReadinessCheck(check_id="backup", status="pass" if recent_verified_backup else "fail", title="Verified backup", explanation="A recent verified platform backup is required."),
            UpgradeReadinessCheck(check_id="audit", status="pass" if audit_chain_valid else "fail", title="Audit integrity", explanation="The audit chain must verify before upgrade."),
            UpgradeReadinessCheck(check_id="packs", status="pass" if unresolved_pack_issues == 0 else "fail", title="Pack compatibility", explanation=f"{unresolved_pack_issues} unresolved pack issues."),
            UpgradeReadinessCheck(check_id="operations", status="pass" if active_operations == 0 else "warn", title="Active operations", explanation=f"{active_operations} active operations should be drained."),
            UpgradeReadinessCheck(check_id="migrations", status="pass" if database_migrations_pending >= 0 else "unknown", title="Migration inventory", explanation=f"{database_migrations_pending} target migrations are expected."),
        ]
        blockers = [item.title for item in checks if item.status == "fail"]
        warnings = [item.title for item in checks if item.status == "warn"]
        return UpgradeReadinessReport(
            report_id=f"upgrade-readiness:{uuid4()}", current_version=current_version, target_version=target_version,
            generated_at_iso=utc_now_iso(), ready=not blockers, checks=checks, blockers=blockers, warnings=warnings,
        )
