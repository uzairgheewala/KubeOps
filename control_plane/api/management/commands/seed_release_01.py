from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from api.models import ScenarioFamilyRecord
from api.services import clear_service_caches, scenario_registry


class Command(BaseCommand):
    help = "Load Release 0.1 scenario-family metadata into the control-plane database."

    def handle(self, *args, **options):
        clear_service_caches()
        registry = scenario_registry()
        source_paths = {
            path.stem: str(path)
            for path in Path(settings.KUBEOPS_SCENARIO_DIR).joinpath("families").glob("*.yaml")
        }
        created = 0
        updated = 0
        for family in registry.values():
            _, was_created = ScenarioFamilyRecord.objects.update_or_create(
                family_id=family.family_id,
                defaults={
                    "version": family.version,
                    "title": family.title,
                    "description": family.description,
                    "parent_family_id": family.parent_family_id,
                    "content_hash": family.content_hash,
                    "payload": family.model_dump(mode="json"),
                    "source_path": source_paths.get(family.family_id, ""),
                },
            )
            created += int(was_created)
            updated += int(not was_created)
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} new and {updated} updated scenario families."))
