from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from kubeops_core.artifacts import build_platform_backup_artifacts
from kubeops_core.models import BackupComponent
from kubeops_core.platform import PlatformRecoveryService

from api.models import AuditEventRecord, OrganizationRecord, PlatformBackupRecord, WorkspaceRecord
from api.release_10 import _store_artifacts
from api.services import pack_runtime


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _component(component_id: str, component_type: str, path: Path, **metadata: object) -> BackupComponent:
    return BackupComponent(
        component_id=component_id,
        component_type=component_type,
        source=path.name,
        payload_hash=_hash(path),
        size_bytes=path.stat().st_size,
        metadata=dict(metadata),
    )


def _tar_directory(source: Path, target: Path, *, arcname: str) -> None:
    with tarfile.open(target, "w:gz") as archive:
        if source.exists():
            archive.add(source, arcname=arcname, recursive=True)


class Command(BaseCommand):
    help = "Create and cryptographically verify a KubeOps platform backup set."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--organization-id", default=settings.KUBEOPS_DEFAULT_ORGANIZATION_ID)
        parser.add_argument("--workspace-id", default=settings.KUBEOPS_DEFAULT_WORKSPACE_ID)
        parser.add_argument("--external-artifact-backup-verified", action="store_true")

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        organization = OrganizationRecord.objects.get(organization_id=options["organization_id"])
        workspace = WorkspaceRecord.objects.get(workspace_id=options["workspace_id"])
        root = Path(settings.KUBEOPS_BACKUP_DIR)
        root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".platform-backup-", dir=root))

        try:
            database_path = staging / "control-plane.json"
            with database_path.open("w", encoding="utf-8") as stream:
                call_command(
                    "dumpdata",
                    "--exclude=contenttypes",
                    "--exclude=auth.permission",
                    "--exclude=sessions",
                    "--exclude=authtoken.token",
                    "--indent=2",
                    stdout=stream,
                )

            config_path = staging / "configuration.tar.gz"
            with tarfile.open(config_path, "w:gz") as archive:
                for relative in [
                    "packs",
                    "profiles",
                    "lifecycle",
                    "policies",
                    "fleets",
                    "governance",
                    "trust",
                    "environments",
                ]:
                    source = Path(settings.REPO_ROOT) / relative
                    if source.exists():
                        archive.add(source, arcname=relative, recursive=True)

            components = [
                _component("database", "database", database_path),
                _component("configuration", "configuration", config_path),
            ]
            payloads: dict[str, Path | bytes] = {
                "database": database_path,
                "configuration": config_path,
            }

            if settings.KUBEOPS_ARTIFACT_BACKEND == "file":
                artifacts_path = staging / "artifacts.tar.gz"
                _tar_directory(Path(settings.KUBEOPS_ARTIFACT_DIR), artifacts_path, arcname="artifacts")
                components.append(_component("artifact-store", "artifact_store", artifacts_path))
                payloads["artifact-store"] = artifacts_path
            else:
                pointer = json.dumps(
                    {
                        "backend": "s3",
                        "bucket": settings.KUBEOPS_ARTIFACT_S3_BUCKET,
                        "prefix": settings.KUBEOPS_ARTIFACT_S3_PREFIX,
                        "endpoint": settings.KUBEOPS_ARTIFACT_S3_ENDPOINT or None,
                        "region": settings.KUBEOPS_ARTIFACT_S3_REGION or None,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                pointer_path = staging / "artifact-store-pointer.json"
                pointer_path.write_bytes(pointer)
                components.append(
                    _component(
                        "artifact-store",
                        "artifact_store",
                        pointer_path,
                        external_backup_required=True,
                        external_backup_verified=bool(options["external_artifact_backup_verified"]),
                    )
                )
                payloads["artifact-store"] = pointer_path

            audit_head = (
                AuditEventRecord.objects.filter(workspace=workspace)
                .order_by("-sequence")
                .values_list("event_hash", flat=True)
                .first()
            )
            service = PlatformRecoveryService()
            manifest = service.build_backup_manifest(
                organization_id=organization.organization_id,
                workspace_id=workspace.workspace_id,
                kubeops_version="1.0.0",
                schema_version="0006",
                components=components,
                pack_resolution_hash=pack_runtime().resolution.content_hash,
                audit_head_hash=audit_head,
                database_vendor=settings.DATABASES["default"]["ENGINE"],
            )
            manifest = service.verify_manifest(manifest, payloads)
            if manifest.status != "verified":
                failures = manifest.metadata.get("verification_failures", [])
                raise CommandError(f"platform backup verification failed: {failures}")

            destination = root / manifest.backup_id.replace(":", "__")
            destination.mkdir(parents=True, exist_ok=False)
            for path in staging.iterdir():
                path.replace(destination / path.name)
            staging.rmdir()

            manifest_path = destination / "manifest.json"
            manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
            PlatformBackupRecord.objects.create(
                backup_id=manifest.backup_id,
                organization=organization,
                workspace=workspace,
                status=manifest.status,
                manifest_hash=manifest.manifest_hash,
                created_at=datetime.fromisoformat(manifest.created_at_iso.replace("Z", "+00:00")),
                payload=manifest.model_dump(mode="json"),
            )
            _store_artifacts(
                build_platform_backup_artifacts(
                    manifest,
                    service.restore_plan(manifest, target_version="1.0.0"),
                )
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created verified platform backup {manifest.backup_id} at {destination}"
                )
            )
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise
