from __future__ import annotations

from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone

from kubeops_core.models import (
    AccessMethodDefinition,
    EnvironmentDefinition,
    ConcurrencyRule,
    ExecutorAgentDefinition,
    FleetDefinition,
    OrganizationDefinition,
    PackTrustPolicy,
    RateLimitRule,
    RetentionPolicy,
    MaintenanceWindow,
    RoleGrant,
    WorkspaceDefinition,
)

from api.models import (
    ArtifactRecord,
    ConcurrencyRuleRecord,
    EnvironmentRecord,
    ExecutorAgentRecord,
    FleetDependencyRecord,
    FleetMembershipRecord,
    FleetRecord,
    OrganizationRecord,
    PackTrustPolicyRecord,
    RateLimitRuleRecord,
    RetentionPolicyRecord,
    MaintenanceWindowRecord,
    RoleGrantRecord,
    ScenarioRunRecord,
    WorkspaceRecord,
)


class Command(BaseCommand):
    help = "Seed Release 1.0 tenancy, fleet, governance, trust, and executor projections."

    def handle(self, *args, **options) -> None:
        organization = OrganizationDefinition(organization_id="default", name="Default organization", slug="default")
        org_record, _ = OrganizationRecord.objects.update_or_create(
            organization_id=organization.organization_id,
            defaults={"name": organization.name, "slug": organization.slug, "active": True, "payload": organization.model_dump(mode="json")},
        )
        workspace = WorkspaceDefinition(workspace_id="default", organization_id="default", name="Default workspace", slug="default")
        workspace_record, _ = WorkspaceRecord.objects.update_or_create(
            workspace_id=workspace.workspace_id,
            defaults={"organization": org_record, "name": workspace.name, "slug": workspace.slug, "active": True, "payload": workspace.model_dump(mode="json")},
        )

        ScenarioRunRecord.objects.filter(organization__isnull=True).update(
            organization=org_record, workspace=workspace_record
        )
        ArtifactRecord.objects.filter(organization__isnull=True).update(
            organization=org_record, workspace=workspace_record
        )

        for record in EnvironmentRecord.objects.all():
            payload = dict(record.payload)
            payload.setdefault("organization_id", organization.organization_id)
            payload.setdefault("workspace_id", workspace.workspace_id)
            record.organization = org_record
            record.workspace = workspace_record
            record.payload = payload
            record.save(update_fields=["organization", "workspace", "payload", "updated_at"])

        source = EnvironmentRecord.objects.filter(environment_id="demo-kind-fixture").first()
        if source:
            fixture_path = Path(settings.REPO_ROOT) / "lab" / "fixtures" / "kind-demo-degraded.v1.yaml"
            k3s = EnvironmentDefinition(
                environment_id="demo-k3s-fixture", organization_id="default", workspace_id="default",
                name="Demo k3s fixture", environment_class="development", provider="local",
                cluster_provider="k3s", host_provider="linux", criticality="standard",
                access_methods=[AccessMethodDefinition(method_id="recorded", method_type="fixture", fixture_path=str(fixture_path))],
                default_access_method_id="recorded", operational_profile_ids=["cluster-observable.v1", "local-development-usable.v1"],
                installed_pack_ids=["generic-kubernetes", "k3s"], labels={"release": "1.0", "mode": "fixture"},
            )
            EnvironmentRecord.objects.update_or_create(
                environment_id=k3s.environment_id,
                defaults={
                    "organization": org_record, "workspace": workspace_record, "name": k3s.name,
                    "environment_class": k3s.environment_class, "provider": k3s.provider,
                    "cluster_provider": k3s.cluster_provider, "host_provider": k3s.host_provider,
                    "criticality": k3s.criticality, "fingerprint": k3s.content_hash,
                    "payload": k3s.model_dump(mode="json"), "active": True,
                },
            )

        fleet_payload = yaml.safe_load((Path(settings.REPO_ROOT) / "fleets" / "demo-fleet.v1.yaml").read_text(encoding="utf-8"))
        fleet = FleetDefinition.model_validate(fleet_payload)
        fleet_record, _ = FleetRecord.objects.update_or_create(
            fleet_id=fleet.fleet_id,
            defaults={
                "organization": org_record, "workspace": workspace_record, "name": fleet.name,
                "max_parallel_operations": fleet.max_parallel_operations, "active": fleet.active,
                "payload": fleet.model_dump(mode="json"),
            },
        )
        fleet_record.memberships.all().delete()
        fleet_record.dependencies.all().delete()
        for member in fleet.members:
            environment = EnvironmentRecord.objects.filter(environment_id=member.environment_id).first()
            if environment:
                FleetMembershipRecord.objects.create(
                    fleet=fleet_record, environment=environment, criticality=member.criticality,
                    failure_domain=member.failure_domain, payload=member.model_dump(mode="json"),
                )
        for dependency in fleet.dependencies:
            source_environment = EnvironmentRecord.objects.filter(environment_id=dependency.source_environment_id).first()
            target_environment = EnvironmentRecord.objects.filter(environment_id=dependency.target_environment_id).first()
            if source_environment and target_environment:
                FleetDependencyRecord.objects.create(
                    dependency_id=dependency.dependency_id, fleet=fleet_record,
                    source_environment=source_environment, target_environment=target_environment,
                    relationship_type=dependency.relationship_type, payload=dependency.model_dump(mode="json"),
                )

        limits_payload = yaml.safe_load(
            (Path(settings.REPO_ROOT) / "governance" / "default-limits.v1.yaml").read_text(encoding="utf-8")
        )
        if limits_payload.get("organization_id") != organization.organization_id or limits_payload.get("workspace_id") != workspace.workspace_id:
            raise ValueError("default governance limits must target the seeded organization and workspace")
        for item in limits_payload.get("rate_rules", []):
            rule = RateLimitRule.model_validate(item)
            RateLimitRuleRecord.objects.update_or_create(
                rule_id=rule.rule_id,
                defaults={
                    "organization": org_record, "workspace": workspace_record, "operation": rule.operation,
                    "enabled": rule.enabled, "payload": rule.model_dump(mode="json"),
                },
            )
        for item in limits_payload.get("concurrency_rules", []):
            rule = ConcurrencyRule.model_validate(item)
            ConcurrencyRuleRecord.objects.update_or_create(
                rule_id=rule.rule_id,
                defaults={
                    "organization": org_record, "workspace": workspace_record,
                    "operation_type": rule.operation_type, "enabled": rule.enabled,
                    "payload": rule.model_dump(mode="json"),
                },
            )

        scheduling_payload = yaml.safe_load(
            (Path(settings.REPO_ROOT) / "governance" / "default-maintenance-windows.v1.yaml").read_text(encoding="utf-8")
        ) or {}
        if scheduling_payload.get("organization_id") != organization.organization_id or scheduling_payload.get("workspace_id") != workspace.workspace_id:
            raise ValueError("default maintenance windows must target the seeded organization and workspace")
        for item in scheduling_payload.get("windows", []):
            window = MaintenanceWindow.model_validate(item)
            MaintenanceWindowRecord.objects.update_or_create(
                window_id=window.window_id,
                defaults={
                    "organization": org_record, "workspace": workspace_record,
                    "enabled": window.enabled, "payload": window.model_dump(mode="json"),
                },
            )

        retention = RetentionPolicy.model_validate(yaml.safe_load((Path(settings.REPO_ROOT) / "governance" / "default-retention.v1.yaml").read_text(encoding="utf-8")))
        RetentionPolicyRecord.objects.update_or_create(
            policy_id=retention.policy_id,
            defaults={"organization": org_record, "workspace": workspace_record, "enabled": retention.enabled, "payload": retention.model_dump(mode="json")},
        )
        trust = PackTrustPolicy.model_validate(yaml.safe_load((Path(settings.REPO_ROOT) / "trust" / "default-pack-trust.v1.yaml").read_text(encoding="utf-8")))
        PackTrustPolicyRecord.objects.update_or_create(
            policy_id=trust.policy_id,
            defaults={"organization": org_record, "workspace": workspace_record, "payload": trust.model_dump(mode="json")},
        )
        admin_grant = RoleGrant(
            grant_id="bootstrap-admin", principal_id="1", role="admin", scope_type="global", scope_id="*",
            granted_by="seed_release_10", granted_at_iso=timezone.now().isoformat(),
        )
        RoleGrantRecord.objects.update_or_create(
            grant_id=admin_grant.grant_id,
            defaults={
                "principal_id": admin_grant.principal_id, "role": admin_grant.role,
                "scope_type": admin_grant.scope_type, "scope_id": admin_grant.scope_id,
                "active": True, "payload": admin_grant.model_dump(mode="json"),
                "granted_at": timezone.now(),
            },
        )
        agent = ExecutorAgentDefinition(
            agent_id="local-executor", organization_id="default", workspace_id="default",
            name="Local guarded executor", status="offline", capabilities={"simulation", "fixture"},
            supported_executor_ids={"simulation", "dry_run"}, environment_ids={"demo-kind-fixture", "demo-k3s-fixture"},
            registered_at_iso=timezone.now().isoformat(),
        )
        ExecutorAgentRecord.objects.update_or_create(
            agent_id=agent.agent_id,
            defaults={
                "organization": org_record, "workspace": workspace_record, "name": agent.name,
                "status": agent.status, "capabilities": sorted(agent.capabilities),
                "supported_executor_ids": sorted(agent.supported_executor_ids),
                "environment_ids": sorted(agent.environment_ids), "max_concurrency": agent.max_concurrency,
                "payload": agent.model_dump(mode="json"),
            },
        )
        from api.services import clear_service_caches
        clear_service_caches()
        call_command("seed_release_05", verbosity=0)
        self.stdout.write(self.style.SUCCESS("Seeded Release 1.0 organization, workspace, fleet, governance, scheduling, trust, role, executor, and trust-aware pack records."))
