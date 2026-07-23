from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kubeops_core.distributed import DistributedDispatcher
from kubeops_core.fleet import FleetService
from kubeops_core.governance import AuditChain, GovernanceLimiter, RetentionPlanner
from kubeops_core.models import (
    AuthorizationRequest,
    BackupComponent,
    ConcurrencyRule,
    ExecutionTask,
    ExecutorAgentDefinition,
    ExecutorHeartbeat,
    FleetDefinition,
    FleetDependency,
    FleetEnvironmentStatus,
    FleetMember,
    KnowledgePackManifest,
    OrganizationDefinition,
    PackTrustPolicy,
    RateLimitRule,
    RetentionPolicy,
    RoleGrant,
    ScopeBinding,
    SecretReference,
    WorkspaceDefinition,
)
from kubeops_core.platform import PlatformRecoveryService
from kubeops_core.secrets import SecretResolver
from kubeops_core.supply_chain import PackSigner
from kubeops_core.tenancy import AuthorizationEngine


def test_hierarchical_authorization_and_capabilities() -> None:
    grant = RoleGrant(
        grant_id="g1", principal_id="alice", role="operator", scope_type="workspace", scope_id="w1",
        granted_at_iso="2026-07-23T00:00:00+00:00",
    )
    engine = AuthorizationEngine(
        [grant],
        [ScopeBinding(child_type="environment", child_id="e1", parent_type="workspace", parent_id="w1")],
    )
    decision = engine.evaluate(
        AuthorizationRequest(
            request_id="r1", principal_id="alice", action="operation.create", scope_type="environment",
            scope_id="e1", required_roles={"operator"}, required_capabilities={"operation.create"},
        ),
        at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )
    assert decision.outcome == "allow"
    assert decision.matched_grant_ids == ["g1"]


def test_fleet_assessment_common_cause_and_ordering() -> None:
    fleet = FleetDefinition(
        fleet_id="f1", organization_id="o1", workspace_id="w1", name="demo",
        members=[FleetMember(environment_id="db"), FleetMember(environment_id="api"), FleetMember(environment_id="ui")],
        dependencies=[
            FleetDependency(dependency_id="d1", source_environment_id="api", target_environment_id="db"),
            FleetDependency(dependency_id="d2", source_environment_id="ui", target_environment_id="api"),
        ],
        max_parallel_operations=2,
    )
    service = FleetService()
    assessment = service.assess(
        fleet,
        [
            FleetEnvironmentStatus(environment_id="db", status="unavailable"),
            FleetEnvironmentStatus(environment_id="api", status="degraded"),
            FleetEnvironmentStatus(environment_id="ui", status="degraded"),
        ],
        incident_families={"db": ["dependency.endpoint_unreachable"], "api": ["dependency.endpoint_unreachable"]},
        shared_factors={"db": {"provider": "kind"}, "api": {"provider": "kind"}},
    )
    assert assessment.status == "unavailable"
    assert len(assessment.common_causes) == 1
    startup = service.plan_operation(fleet, "startup")
    assert [wave.environment_ids for wave in startup.waves] == [["db"], ["api"], ["ui"]]
    shutdown = service.plan_operation(fleet, "shutdown")
    assert [wave.environment_ids for wave in shutdown.waves] == [["ui"], ["api"], ["db"]]


def test_distributed_dispatcher_enforces_capability_and_lease() -> None:
    dispatcher = DistributedDispatcher()
    agent = ExecutorAgentDefinition(
        agent_id="a1", organization_id="o1", workspace_id="w1", name="agent", status="online",
        capabilities={"kubernetes.restart"}, supported_executor_ids={"kubectl"}, environment_ids={"e1"},
        registered_at_iso="2026-07-23T00:00:00+00:00",
    )
    dispatcher.register_agent(agent)
    dispatcher.heartbeat(ExecutorHeartbeat(
        heartbeat_id="h1", agent_id="a1", occurred_at_iso="2026-07-23T00:00:00+00:00",
        status="online", available_capacity=1, capabilities={"kubernetes.restart"},
    ))
    task = ExecutionTask(
        task_id="t1", organization_id="o1", workspace_id="w1", operation_id="op1", action_id="act1",
        environment_id="e1", action_type_id="restart", executor_id="kubectl",
        required_capabilities={"kubernetes.restart"}, payload_hash="abc",
        created_at_iso="2026-07-23T00:00:00+00:00", updated_at_iso="2026-07-23T00:00:00+00:00",
    )
    dispatcher.enqueue(task)
    decision, lease = dispatcher.dispatch("t1", at=datetime(2026, 7, 23, tzinfo=timezone.utc))
    assert decision.outcome == "assigned"
    assert lease is not None
    completed = dispatcher.complete(
        lease.lease_id, lease.nonce, success=True,
        at=datetime(2026, 7, 23, 0, 0, 1, tzinfo=timezone.utc),
    )
    assert completed.status == "completed"


def test_audit_chain_detects_tampering_and_exports() -> None:
    chain = AuditChain()
    chain.append(organization_id="o1", workspace_id="w1", principal_id="alice", action="read", resource_type="fleet", resource_id="f1", outcome="allowed")
    chain.append(organization_id="o1", workspace_id="w1", principal_id="alice", action="operate", resource_type="fleet", resource_id="f1", outcome="allowed")
    assert chain.verify().valid
    export, payload = chain.export("o1", "w1")
    assert export.payload_hash
    assert payload.count("\n") == 2
    corrupted = chain.events[1].model_copy(update={"event_hash": "bad"})
    assert not AuditChain([chain.events[0], corrupted]).verify().valid


def test_rate_concurrency_and_retention_governance() -> None:
    limiter = GovernanceLimiter(
        [RateLimitRule(rule_id="r", scope_type="workspace", scope_id="w1", operation="create", limit=1, window_seconds=60)],
        [ConcurrencyRule(rule_id="c", scope_type="workspace", scope_id="w1", maximum_active=1)],
    )
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    assert limiter.evaluate(scope_type="workspace", scope_id="w1", operation="create", active_count=0, at=now).outcome == "allow"
    assert limiter.evaluate(scope_type="workspace", scope_id="w1", operation="create", active_count=0, at=now).outcome == "delay"
    assert limiter.evaluate(scope_type="workspace", scope_id="w1", operation="other", active_count=1, at=now).outcome == "delay"

    policy = RetentionPolicy(policy_id="p", organization_id="o1", scope_id="w1", artifact_retention_days=10)
    plan = RetentionPlanner().plan(policy, [
        {"resource_type": "artifact", "resource_id": "old", "created_at_iso": (now - timedelta(days=11)).isoformat(), "size_bytes": 10},
        {"resource_type": "operation", "resource_id": "failed", "created_at_iso": (now - timedelta(days=400)).isoformat(), "status": "failed", "size_bytes": 20},
    ], at=now)
    assert plan.eligible_candidate_ids == ["retention:artifact:old"]
    assert "retention:operation:failed" in plan.protected_candidate_ids


def test_secret_resolution_is_scoped_and_never_returns_material_in_receipt() -> None:
    reference = SecretReference(
        secret_ref_id="s1", organization_id="o1", workspace_id="w1", provider="memory", locator="pack-key",
        allowed_consumers={"signer"},
    )
    value, receipt = SecretResolver({"pack-key": "super-secret"}).resolve(reference, "signer")
    assert value == "super-secret"
    assert "super-secret" not in receipt.canonical_json()


def test_pack_signing_and_trust_policy() -> None:
    manifest = KnowledgePackManifest(pack_id="demo", version="1.0.0", title="Demo", pack_kind="integration")
    signature = PackSigner.sign(manifest, key_id="key1", secret="secret", signer="release-bot")
    policy = PackTrustPolicy(
        policy_id="trust", organization_id="o1", workspace_id="w1", trusted_key_ids={"key1"},
        trusted_signers={"release-bot"},
    )
    result = PackSigner.verify(manifest, signature, policy, trusted_secrets={"key1": "secret"})
    assert result.outcome == "trusted"
    assert PackSigner.verify(manifest, signature, policy, trusted_secrets={"key1": "wrong"}).outcome == "invalid"


def test_platform_backup_restore_and_upgrade_readiness() -> None:
    service = PlatformRecoveryService()
    manifest = service.build_backup_manifest(
        organization_id="o1", workspace_id="w1", kubeops_version="1.0.0", schema_version="0006",
        components=[BackupComponent(component_id="db", component_type="database", source="postgres", payload_hash="abc")],
        audit_head_hash="head",
    )
    assert manifest.status == "created"
    verified = service.verify_manifest(manifest, {"db": b"payload"})
    assert verified.status == "invalid"
    component_hash = __import__("hashlib").sha256(b"payload").hexdigest()
    manifest = service.build_backup_manifest(
        organization_id="o1", workspace_id="w1", kubeops_version="1.0.0", schema_version="0006",
        components=[BackupComponent(component_id="db", component_type="database", source="postgres", payload_hash=component_hash)],
        audit_head_hash="head",
    )
    manifest = service.verify_manifest(manifest, {"db": b"payload"})
    assert manifest.status == "verified"
    restore = service.restore_plan(manifest, target_version="1.0.1")
    assert restore.compatible
    report = service.upgrade_readiness(
        current_version="1.0.0", target_version="1.1.0", database_migrations_pending=1,
        unresolved_pack_issues=0, audit_chain_valid=True, recent_verified_backup=True, active_operations=0,
    )
    assert report.ready


def test_tenancy_models_are_stable() -> None:
    org = OrganizationDefinition(organization_id="o1", name="Org", slug="org")
    workspace = WorkspaceDefinition(workspace_id="w1", organization_id="o1", name="Workspace", slug="workspace")
    assert org.content_hash
    assert workspace.organization_id == org.organization_id


def test_pack_manager_enforces_trust_during_runtime_resolution() -> None:
    from kubeops_core.packs import PackManager

    manifest = KnowledgePackManifest(pack_id="signed", version="1.0.0", title="Signed", pack_kind="integration")
    manager = PackManager(kubeops_version="1.0.0")
    manager.register(manifest)
    policy = PackTrustPolicy(
        policy_id="strict", organization_id="o1", workspace_id="w1",
        trusted_key_ids={"key1"}, trusted_signers={"release-bot"},
    )
    unsigned = manager.runtime(["signed"], trust_policy=policy)
    assert unsigned.active_pack_ids == []
    assert unsigned.resolution.blocked_pack_ids == ["signed"]
    signature = PackSigner.sign(manifest, key_id="key1", secret="secret", signer="release-bot")
    trusted = manager.runtime(
        ["signed"], trust_policy=policy, signatures={"signed": signature},
        trusted_secrets={"key1": "secret"},
    )
    assert trusted.active_pack_ids == ["signed"]


def test_expired_role_grant_does_not_authorize() -> None:
    grant = RoleGrant(
        grant_id="expired", principal_id="alice", role="admin", scope_type="global", scope_id="*",
        granted_at_iso="2026-01-01T00:00:00+00:00", expires_at_iso="2026-01-02T00:00:00+00:00",
    )
    decision = AuthorizationEngine([grant]).evaluate(
        AuthorizationRequest(
            request_id="expired-request", principal_id="alice", action="delete",
            scope_type="global", scope_id="*", required_roles={"admin"},
        ),
        at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )
    assert decision.outcome == "deny"


def test_dispatcher_expiration_requeues_bounded_task() -> None:
    dispatcher = DistributedDispatcher()
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    dispatcher.register_agent(ExecutorAgentDefinition(
        agent_id="a", organization_id="o", workspace_id="w", name="a", status="online",
        supported_executor_ids={"dry_run"}, lease_ttl_seconds=5,
        registered_at_iso=now.isoformat(),
    ))
    task = ExecutionTask(
        task_id="retry", organization_id="o", workspace_id="w", operation_id="op", action_id="a",
        environment_id="e", action_type_id="wait", executor_id="dry_run", payload_hash="h",
        max_attempts=2, created_at_iso=now.isoformat(), updated_at_iso=now.isoformat(),
    )
    dispatcher.enqueue(task)
    _, lease = dispatcher.dispatch(task.task_id, at=now)
    assert lease is not None
    assert dispatcher.expire(at=now + timedelta(seconds=6)) == [lease.lease_id]
    assert dispatcher.tasks[task.task_id].status == "queued"
    assert dispatcher.tasks[task.task_id].attempt == 2


def test_retention_legal_hold_overrides_expiry() -> None:
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    policy = RetentionPolicy(
        policy_id="hold", organization_id="o", scope_id="w", artifact_retention_days=1,
        legal_hold_labels={"case": "alpha"},
    )
    plan = RetentionPlanner().plan(policy, [{
        "resource_type": "artifact", "resource_id": "evidence",
        "created_at_iso": (now - timedelta(days=30)).isoformat(), "labels": {"case": "alpha"},
    }], at=now)
    assert plan.eligible_candidate_ids == []
    assert plan.protected_candidate_ids == ["retention:artifact:evidence"]


def test_s3_artifact_store_is_immutable_and_round_trips() -> None:
    import io
    from kubeops_core.artifacts import S3ArtifactStore
    from kubeops_core.models import OperationalArtifact

    class Missing(Exception):
        response = {"Error": {"Code": "NoSuchKey"}}

    class FakeS3:
        def __init__(self) -> None:
            self.items: dict[tuple[str, str], bytes] = {}
        def get_object(self, *, Bucket: str, Key: str):
            try: value = self.items[(Bucket, Key)]
            except KeyError as exc: raise Missing() from exc
            return {"Body": io.BytesIO(value)}
        def put_object(self, *, Bucket: str, Key: str, Body: bytes, **kwargs):
            self.items[(Bucket, Key)] = Body

    client = FakeS3()
    store = S3ArtifactStore("bucket", prefix="test", client=client)
    artifact = OperationalArtifact(
        artifact_id="example:abc", scope_type="test", scope_id="scope", artifact_type="example",
        payload_hash="abc", payload={"ok": True},
    )
    assert store.put(artifact).startswith("s3://bucket/test/scope/")
    assert store.put(artifact).startswith("s3://bucket/test/scope/")
    assert store.get("scope", "example:abc").payload == {"ok": True}
    changed = artifact.model_copy(update={"payload": {"ok": False}})
    import pytest
    with pytest.raises(ValueError, match="immutable artifact collision"):
        store.put(changed)


def test_ed25519_pack_signing_separates_signing_and_verification_material() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    manifest = KnowledgePackManifest(
        pack_id="asymmetric", version="1.0.0", title="Asymmetric", pack_kind="integration"
    )
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    signature = PackSigner.sign(
        manifest,
        key_id="release-ed25519",
        secret=private_pem,
        signer="release-bot",
        scheme="ed25519",
    )
    policy = PackTrustPolicy(
        policy_id="strict-asymmetric",
        organization_id="o1",
        workspace_id="w1",
        require_asymmetric=True,
        allowed_schemes={"ed25519"},
        trusted_key_ids={"release-ed25519"},
        trusted_signers={"release-bot"},
    )
    result = PackSigner.verify(
        manifest,
        signature,
        policy,
        trusted_public_keys={"release-ed25519": public_pem},
    )
    assert result.outcome == "trusted"
    assert "PRIVATE KEY" not in result.canonical_json()


def test_platform_manifest_hash_detects_metadata_component_tampering() -> None:
    import hashlib

    service = PlatformRecoveryService()
    payload = b"database"
    manifest = service.build_backup_manifest(
        organization_id="o1",
        workspace_id="w1",
        kubeops_version="1.0.0",
        schema_version="0006",
        components=[
            BackupComponent(
                component_id="db",
                component_type="database",
                source="control-plane.json",
                payload_hash=hashlib.sha256(payload).hexdigest(),
            )
        ],
    )
    assert service.verify_manifest(manifest, {"db": payload}).status == "verified"
    tampered_component = manifest.components[0].model_copy(update={"source": "other.json"})
    tampered = manifest.model_copy(update={"components": [tampered_component]})
    verified = service.verify_manifest(tampered, {"db": payload})
    assert verified.status == "invalid"
    assert "manifest hash mismatch" in verified.metadata["verification_failures"]


def test_release_10_cli_registers_all_production_command_groups() -> None:
    from typer.testing import CliRunner
    from kubeops_cli.main import app

    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ["access", "fleet", "executor", "audit", "retention", "platform", "security"]:
        assert command in result.stdout


def test_distributed_receipts_reconcile_and_live_verification_seal(tmp_path) -> None:
    from kubeops_core.actions import build_builtin_action_catalog
    from kubeops_core.execution import (
        ExecutionContext,
        FileOperationStore,
        OperationRuntime,
        RuntimeContext,
        build_default_executor_registry,
    )
    from kubeops_core.models import ActionInstance, ActionReceipt, RecoveryPlan
    from kubeops_core.policy import PolicyContext
    from kubeops_core.util import utc_now_iso

    action = ActionInstance(
        action_id="wait",
        action_type_id="operation.wait_for_condition.v1",
        parameters={"condition_satisfied": True},
    )
    plan = RecoveryPlan(
        plan_id="plan:distributed",
        environment_id="env",
        objective_id="objective",
        actions=[action],
        mode="guarded_execution",
    )
    runtime = OperationRuntime(
        build_builtin_action_catalog(),
        build_default_executor_registry(),
        FileOperationStore(tmp_path),
    )
    operation = runtime.create("env", plan, mode="guarded_execution")
    now = utc_now_iso()
    receipt = ActionReceipt(
        receipt_id="receipt:distributed",
        operation_id=operation.operation_id,
        action_id="wait",
        action_type_id=action.action_type_id,
        executor_id="builtin.wait",
        status="completed",
        started_at_iso=now,
        completed_at_iso=now,
    )
    operation = runtime.reconcile_external_receipts(operation, [receipt])
    assert operation.status == "verifying"
    assert operation.plan.actions[0].status == "completed"
    context = RuntimeContext(
        policy_context=PolicyContext(
            environment_class="development",
            environment_fingerprint="fingerprint",
            expected_fingerprint="fingerprint",
            capabilities=frozenset(),
        ),
        execution_context=ExecutionContext(
            operation_id=operation.operation_id,
            mode="live",
            environment_id="env",
        ),
        world_provider=lambda: {},
    )
    sealed = runtime.verify_external(operation, context)
    assert sealed.status == "completed"
    assert sealed.recovery_certificate is not None
    assert sealed.recovery_certificate.status == "recovered"


def test_dispatch_rejects_nonqueued_task() -> None:
    dispatcher = DistributedDispatcher()
    dispatcher.register_agent(
        ExecutorAgentDefinition(
            agent_id="agent",
            organization_id="o",
            workspace_id="w",
            name="Agent",
            status="online",
            supported_executor_ids={"dry_run"},
            registered_at_iso="2026-07-23T00:00:00+00:00",
        )
    )
    task = ExecutionTask(
        task_id="done",
        organization_id="o",
        workspace_id="w",
        operation_id="op",
        action_id="a",
        environment_id="env",
        action_type_id="wait",
        executor_id="dry_run",
        status="completed",
        payload_hash="hash",
        created_at_iso="2026-07-23T00:00:00+00:00",
        updated_at_iso="2026-07-23T00:00:00+00:00",
    )
    dispatcher.enqueue(task)
    decision, lease = dispatcher.dispatch(task.task_id)
    assert decision.outcome == "rejected"
    assert lease is None


def test_empty_platform_backup_cannot_be_verified() -> None:
    service = PlatformRecoveryService()
    manifest = service.build_backup_manifest(
        organization_id="o1", workspace_id="w1", kubeops_version="1.0.0",
        schema_version="0006", components=[],
    )
    verified = service.verify_manifest(manifest, {})
    assert verified.status == "invalid"
    assert "no restorable components" in verified.metadata["verification_failures"][0]
    assert not service.restore_plan(verified, target_version="1.0.0").compatible


def test_maintenance_windows_delay_ready_and_expire_schedules() -> None:
    from kubeops_core.models import MaintenanceWindow, ScheduledOperation
    from kubeops_core.scheduling import SchedulingService

    service = SchedulingService()
    window = MaintenanceWindow(
        window_id="weekday-window", organization_id="o", workspace_id="w", name="Weekday",
        timezone="Asia/Karachi", days_of_week={3}, start_local_time="20:00", duration_minutes=120,
        allowed_operation_types={"startup"}, target_ids={"env"},
    )
    schedule = ScheduledOperation(
        schedule_id="s", organization_id="o", workspace_id="w", target_type="environment",
        target_id="env", operation_type="startup", lifecycle_profile_id="local-development-startup.v1",
        maintenance_window_id=window.window_id, created_by="alice",
        created_at_iso="2026-07-23T00:00:00+00:00", updated_at_iso="2026-07-23T00:00:00+00:00",
    )
    before = service.evaluate(schedule, [window], at=datetime(2026, 7, 23, 14, 0, tzinfo=timezone.utc))
    assert before.outcome == "delay"
    assert before.next_eligible_at_iso == "2026-07-23T15:00:00+00:00"
    ready = service.evaluate(schedule, [window], at=datetime(2026, 7, 23, 15, 30, tzinfo=timezone.utc))
    assert ready.outcome == "ready"
    expired_schedule = schedule.model_copy(update={"deadline_iso": "2026-07-23T14:30:00+00:00"})
    expired = service.evaluate(expired_schedule, [window], at=datetime(2026, 7, 23, 14, 0, tzinfo=timezone.utc))
    assert expired.outcome == "expired"


def test_scheduled_operation_requires_lifecycle_profile_for_environment() -> None:
    import pytest
    from pydantic import ValidationError
    from kubeops_core.models import ScheduledOperation

    with pytest.raises(ValidationError, match="lifecycle_profile_id"):
        ScheduledOperation(
            schedule_id="s", organization_id="o", workspace_id="w", target_type="environment",
            target_id="env", operation_type="startup", created_by="alice",
            created_at_iso="2026-07-23T00:00:00+00:00", updated_at_iso="2026-07-23T00:00:00+00:00",
        )


def test_schedule_decisions_are_deterministic_for_same_evaluation_instant() -> None:
    from kubeops_core.models import MaintenanceWindow, ScheduledOperation
    from kubeops_core.scheduling import SchedulingService

    instant = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    window = MaintenanceWindow(
        window_id="all-day", organization_id="o", workspace_id="w", name="All day",
        timezone="UTC", days_of_week=set(range(7)), start_local_time="00:00",
        duration_minutes=1440, allowed_operation_types={"startup"}, target_ids={"env"},
    )
    schedule = ScheduledOperation(
        schedule_id="deterministic", organization_id="o", workspace_id="w",
        target_type="environment", target_id="env", operation_type="startup",
        lifecycle_profile_id="local-development-startup.v1", maintenance_window_id="all-day",
        created_by="test", created_at_iso=instant.isoformat(), updated_at_iso=instant.isoformat(),
    )
    first = SchedulingService().evaluate(schedule, [window], at=instant)
    second = SchedulingService().evaluate(schedule, [window], at=instant)
    assert first == second
    assert first.decision_id == second.decision_id


def test_scheduled_operation_rejects_inverted_time_bounds() -> None:
    import pytest
    from pydantic import ValidationError
    from kubeops_core.models import ScheduledOperation

    with pytest.raises(ValidationError, match="deadline_iso"):
        ScheduledOperation(
            schedule_id="inverted", organization_id="o", workspace_id="w",
            target_type="environment", target_id="env", operation_type="startup",
            lifecycle_profile_id="local-development-startup.v1", created_by="test",
            created_at_iso="2026-07-23T00:00:00+00:00",
            updated_at_iso="2026-07-23T00:00:00+00:00",
            not_before_iso="2026-07-24T00:00:00+00:00",
            deadline_iso="2026-07-23T00:00:00+00:00",
        )


def _release_10_task(*, task_id: str = "task", status: str = "queued", max_attempts: int = 2) -> ExecutionTask:
    return ExecutionTask(
        task_id=task_id,
        organization_id="o",
        workspace_id="w",
        operation_id="op",
        action_id="action",
        environment_id="env",
        action_type_id="wait",
        executor_id="dry_run",
        status=status,
        max_attempts=max_attempts,
        payload_hash="payload-hash",
        created_at_iso="2026-07-23T00:00:00+00:00",
        updated_at_iso="2026-07-23T00:00:00+00:00",
    )


def test_distributed_enqueue_is_idempotent_and_does_not_reset_terminal_state() -> None:
    dispatcher = DistributedDispatcher()
    completed = _release_10_task(status="completed")
    dispatcher.enqueue(completed)
    dispatcher.enqueue(_release_10_task(status="queued"))
    assert dispatcher.tasks[completed.task_id].status == "completed"


def test_distributed_agent_identity_is_immutable() -> None:
    import pytest

    dispatcher = DistributedDispatcher()
    base = ExecutorAgentDefinition(
        agent_id="agent", organization_id="o", workspace_id="w", name="Agent",
        status="online", public_identity="spiffe://o/w/agent",
        supported_executor_ids={"dry_run"}, registered_at_iso="2026-07-23T00:00:00+00:00",
    )
    dispatcher.register_agent(base)
    with pytest.raises(ValueError, match="different tenant or public identity"):
        dispatcher.register_agent(base.model_copy(update={"workspace_id": "other"}))


def test_distributed_expired_lease_cannot_be_renewed_or_completed() -> None:
    import pytest

    dispatcher = DistributedDispatcher()
    dispatcher.register_agent(ExecutorAgentDefinition(
        agent_id="agent", organization_id="o", workspace_id="w", name="Agent",
        status="online", supported_executor_ids={"dry_run"}, max_concurrency=1,
        lease_ttl_seconds=5, registered_at_iso="2026-07-23T00:00:00+00:00",
    ))
    dispatcher.enqueue(_release_10_task())
    start = datetime(2026, 7, 23, tzinfo=timezone.utc)
    _, lease = dispatcher.dispatch("task", at=start)
    assert lease is not None
    after_expiry = start + timedelta(seconds=6)
    with pytest.raises(ValueError, match="expired"):
        dispatcher.renew(lease.lease_id, lease.nonce, at=after_expiry)
    with pytest.raises(ValueError):
        dispatcher.complete(lease.lease_id, lease.nonce, success=True, at=after_expiry)
    assert dispatcher.tasks["task"].status == "queued"


def test_distributed_heartbeat_capacity_is_enforced() -> None:
    dispatcher = DistributedDispatcher()
    dispatcher.register_agent(ExecutorAgentDefinition(
        agent_id="agent", organization_id="o", workspace_id="w", name="Agent",
        status="online", supported_executor_ids={"dry_run"}, max_concurrency=3,
        registered_at_iso="2026-07-23T00:00:00+00:00",
    ))
    dispatcher.heartbeat(ExecutorHeartbeat(
        heartbeat_id="hb", agent_id="agent", occurred_at_iso="2026-07-23T00:00:00+00:00",
        status="online", available_capacity=0,
    ))
    dispatcher.enqueue(_release_10_task())
    decision, lease = dispatcher.dispatch("task", at=datetime(2026, 7, 23, tzinfo=timezone.utc))
    assert decision.outcome == "queued"
    assert lease is None


def test_governance_and_retention_use_supplied_evaluation_time() -> None:
    now = datetime(2026, 7, 23, 12, 34, tzinfo=timezone.utc)
    decision = GovernanceLimiter().evaluate(
        scope_type="workspace", scope_id="w", operation="read", at=now,
    )
    assert decision.evaluated_at_iso == now.isoformat()
    plan = RetentionPlanner().plan(
        RetentionPolicy(policy_id="p-time", organization_id="o", scope_id="w"),
        [],
        at=now,
    )
    assert plan.generated_at_iso == now.isoformat()


def test_restore_compatibility_tracks_backup_major_version() -> None:
    import hashlib

    service = PlatformRecoveryService()
    payload = b"db"
    manifest = service.build_backup_manifest(
        organization_id="o", workspace_id="w", kubeops_version="2.1.0", schema_version="0007",
        components=[BackupComponent(
            component_id="db", component_type="database", source="db.json",
            payload_hash=hashlib.sha256(payload).hexdigest(),
        )],
    )
    verified = service.verify_manifest(manifest, {"db": payload})
    assert service.restore_plan(verified, target_version="2.9.0").compatible
    assert not service.restore_plan(verified, target_version="3.0.0").compatible
