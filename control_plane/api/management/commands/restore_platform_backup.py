from __future__ import annotations

import os
import shutil
import tarfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from kubeops_core.models import ControlPlaneBackupManifest
from kubeops_core.platform import PlatformRecoveryService

from api.models import OperationRecord


def _safe_extract(archive: tarfile.TarFile, target: Path) -> None:
    target_resolved = target.resolve()
    members = archive.getmembers()
    for member in members:
        destination = (target / member.name).resolve()
        if target_resolved not in destination.parents and destination != target_resolved:
            raise CommandError(f"unsafe archive member {member.name!r}")
        if member.issym() or member.islnk() or member.isdev():
            raise CommandError(f"unsafe archive member type for {member.name!r}")
    try:
        archive.extractall(target, members=members, filter="data")
    except TypeError:  # pragma: no cover - Python < 3.12 compatibility
        archive.extractall(target, members=members)


def _component_path(directory: Path, source: str) -> Path:
    candidate = Path(source)
    if candidate.is_absolute():
        raise CommandError(f"backup component source must be relative: {source!r}")
    resolved = (directory / candidate).resolve()
    directory_resolved = directory.resolve()
    if directory_resolved not in resolved.parents and resolved != directory_resolved:
        raise CommandError(f"backup component escapes its backup directory: {source!r}")
    return resolved


def _payloads(manifest: ControlPlaneBackupManifest, directory: Path) -> dict[str, Path]:
    payloads: dict[str, Path] = {}
    for component in manifest.components:
        path = _component_path(directory, component.source)
        if path.exists() and path.is_file():
            payloads[component.component_id] = path
    return payloads


class Command(BaseCommand):
    help = "Render or explicitly apply a freshly verified KubeOps platform restore plan."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("manifest", type=Path)
        parser.add_argument("--target-version", default="1.0.0")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm-backup-id", default="")

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        manifest_path: Path = options["manifest"].resolve()
        manifest = ControlPlaneBackupManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        service = PlatformRecoveryService()
        fresh_manifest = service.verify_manifest(manifest, _payloads(manifest, manifest_path.parent))
        plan = service.restore_plan(fresh_manifest, target_version=options["target_version"])
        self.stdout.write(plan.model_dump_json(indent=2))
        if not options["apply"]:
            return

        if os.getenv("KUBEOPS_RESTORE_ENABLED", "0") != "1":
            raise CommandError(
                "restore is disabled; set KUBEOPS_RESTORE_ENABLED=1 only in a controlled recovery window"
            )
        if options["confirm_backup_id"] != manifest.backup_id:
            raise CommandError("--confirm-backup-id must exactly match the manifest backup_id")
        if manifest.status != "verified" or fresh_manifest.status != "verified" or not plan.compatible:
            failures = fresh_manifest.metadata.get("verification_failures", [])
            raise CommandError(
                f"backup failed fresh verification or target version is incompatible: {failures}"
            )
        if OperationRecord.objects.exclude(
            status__in=["completed", "failed", "cancelled"]
        ).exists():
            raise CommandError("active operations must be drained before control-plane restore")

        directory = manifest_path.parent
        component_by_type = {item.component_type: item for item in manifest.components}
        database_component = component_by_type.get("database")
        configuration_component = component_by_type.get("configuration")
        artifact_component = component_by_type.get("artifact_store")
        if database_component is None:
            raise CommandError("database backup component is unavailable")
        database_path = _component_path(directory, database_component.source)

        call_command("flush", "--noinput")
        call_command("loaddata", str(database_path))

        if artifact_component is not None and settings.KUBEOPS_ARTIFACT_BACKEND == "file":
            artifact_archive = _component_path(directory, artifact_component.source)
            target = Path(settings.KUBEOPS_ARTIFACT_DIR)
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            with tarfile.open(artifact_archive, "r:gz") as archive:
                _safe_extract(archive, target.parent)

        if configuration_component is not None:
            configuration_archive = _component_path(directory, configuration_component.source)
            with tarfile.open(configuration_archive, "r:gz") as archive:
                _safe_extract(archive, Path(settings.REPO_ROOT))

        self.stdout.write(
            self.style.SUCCESS(
                f"Restored verified database, artifact, and configuration components from {manifest.backup_id}"
            )
        )
