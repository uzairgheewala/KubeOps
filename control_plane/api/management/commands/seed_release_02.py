from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from kubeops_core.models import AccessMethodDefinition, EnvironmentDefinition

from api.models import EnvironmentRecord, OperationalProfileRecord
from api.services import profile_registry


class Command(BaseCommand):
    help = "Seed Release 0.2 operational profiles and the fixture-backed demo environment."

    def handle(self, *args, **options) -> None:
        profile_count = 0
        for profile in profile_registry().values():
            OperationalProfileRecord.objects.update_or_create(
                profile_id=profile.profile_id,
                defaults={
                    "version": profile.version,
                    "title": profile.title,
                    "description": profile.description,
                    "content_hash": profile.content_hash,
                    "payload": profile.model_dump(mode="json"),
                    "source_path": profile_registry().source(profile.profile_id),
                },
            )
            profile_count += 1

        fixture_path = Path(settings.REPO_ROOT) / "lab" / "fixtures" / "kind-demo-degraded.v1.yaml"
        environment = EnvironmentDefinition(
            environment_id="demo-kind-fixture",
            name="Demo Kind fixture",
            environment_class="development",
            provider="local",
            cluster_provider="kind",
            host_provider="docker",
            criticality="disposable",
            access_methods=[
                AccessMethodDefinition(
                    method_id="recorded-degraded",
                    method_type="fixture",
                    title="Recorded degraded Kind fixture",
                    fixture_path=str(fixture_path),
                    read_only=True,
                ),
                AccessMethodDefinition(
                    method_id="recorded-healthy",
                    method_type="fixture",
                    title="Recorded healthy Kind fixture",
                    fixture_path=str(Path(settings.REPO_ROOT) / "lab" / "fixtures" / "kind-demo-healthy.v1.yaml"),
                    read_only=True,
                ),
            ],
            default_access_method_id="recorded-degraded",
            operational_profile_ids=["cluster-observable.v1", "local-development-usable.v1"],
            installed_pack_ids=["generic-kubernetes", "kind"],
            labels={"release": "0.2", "mode": "fixture"},
            metadata={
                "description": "A deterministic fixture-backed environment for the Release 0.2 workbench.",
                "healthy_fixture_path": str(Path(settings.REPO_ROOT) / "lab" / "fixtures" / "kind-demo-healthy.v1.yaml"),
            },
        )
        EnvironmentRecord.objects.update_or_create(
            environment_id=environment.environment_id,
            defaults={
                "name": environment.name,
                "environment_class": environment.environment_class,
                "provider": environment.provider,
                "cluster_provider": environment.cluster_provider,
                "host_provider": environment.host_provider,
                "criticality": environment.criticality,
                "fingerprint": environment.content_hash,
                "payload": environment.model_dump(mode="json"),
                "active": True,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Seeded {profile_count} operational profiles and demo-kind-fixture."))
