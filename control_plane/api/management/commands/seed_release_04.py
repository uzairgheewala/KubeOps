from __future__ import annotations

from django.core.management.base import BaseCommand

from api.models import ExecutionPolicyRecord, LifecycleProfileRecord
from api.services import clear_service_caches, lifecycle_registry, policy_registry


class Command(BaseCommand):
    help = "Seed Release 0.4 lifecycle profiles and execution policies."

    def handle(self, *args, **options) -> None:
        clear_service_caches()
        lifecycle = lifecycle_registry()
        policies = policy_registry()

        lifecycle_count = 0
        for profile in lifecycle.values():
            LifecycleProfileRecord.objects.update_or_create(
                profile_id=profile.profile_id,
                defaults={
                    "version": profile.version,
                    "title": profile.title,
                    "operation_type": profile.operation_type,
                    "target_operational_profile_id": profile.target_operational_profile_id,
                    "content_hash": profile.content_hash,
                    "payload": profile.model_dump(mode="json"),
                    "source_path": lifecycle.source(profile.profile_id),
                },
            )
            lifecycle_count += 1

        policy_count = 0
        for policy in policies.values():
            ExecutionPolicyRecord.objects.update_or_create(
                policy_id=policy.policy_id,
                defaults={
                    "title": policy.title,
                    "content_hash": policy.content_hash,
                    "payload": policy.model_dump(mode="json"),
                    "source_path": policies.source(policy.policy_id),
                },
            )
            policy_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {lifecycle_count} lifecycle profiles and {policy_count} execution policies."
            )
        )
