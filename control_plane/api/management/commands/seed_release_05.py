from __future__ import annotations

from django.core.management.base import BaseCommand

from api.models import KnowledgePackRecord
from api.services import clear_service_caches, pack_manager, pack_runtime


class Command(BaseCommand):
    help = "Seed Release 0.5 knowledge-pack manifests and resolution status."

    def handle(self, *args, **options) -> None:
        clear_service_caches()
        manager = pack_manager()
        resolution = pack_runtime().resolution
        status_by_id = {item.pack_id: item for item in resolution.statuses}
        for manifest in manager.values():
            status = status_by_id.get(manifest.pack_id)
            KnowledgePackRecord.objects.update_or_create(
                pack_id=manifest.pack_id,
                defaults={
                    "version": manifest.version,
                    "title": manifest.title,
                    "pack_kind": manifest.pack_kind,
                    "state": status.state if status else "disabled",
                    "enabled": manifest.pack_id in resolution.active_pack_ids,
                    "source_path": manager.source(manifest.pack_id),
                    "manifest_hash": manifest.content_hash,
                    "contribution_counts": manifest.contributions.counts(),
                    "capabilities": sorted(manifest.capabilities),
                    "payload": manifest.model_dump(mode="json"),
                    "validation_issues": [item.model_dump(mode="json") for item in (status.issues if status else [])],
                },
            )
        installed_ids = [manifest.pack_id for manifest in manager.values()]
        KnowledgePackRecord.objects.exclude(pack_id__in=installed_ids).delete()
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(installed_ids)} knowledge packs; {len(resolution.active_pack_ids)} active."))
