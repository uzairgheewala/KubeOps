from __future__ import annotations

from pathlib import Path

from kubeops_core.actions import build_builtin_action_catalog
from kubeops_core.environments import EnvironmentIntelligenceService
from kubeops_core.execution import (
    CommandRunner,
    ExecutionContext,
    FileOperationStore,
    OperationRuntime,
    RuntimeContext,
    build_default_executor_registry,
)
from kubeops_core.lifecycle import LifecyclePlanner, LifecycleProfileRegistry
from kubeops_core.models import (
    ApprovalRecord,
    EnvironmentDefinition,
    ExecutionPolicy,
    RecoveryPlan,
    VerificationCondition,
)
from kubeops_core.policy import ExecutionPolicyRegistry, PolicyContext, PolicyEngine
from kubeops_core.profiles import OperationalProfileRegistry
from kubeops_core.models.predicate import FieldEquals
from kubeops_core.util import utc_now_iso


def _snapshot(repo_root: Path):
    fixture = repo_root / "lab" / "fixtures" / "kind-demo-degraded.v1.yaml"
    environment = EnvironmentDefinition(
        environment_id="release-04",
        name="Release 0.4",
        environment_class="development",
        provider="fixture",
        cluster_provider="kind",
        access_methods=[{"method_id": "fixture", "method_type": "fixture", "title": "fixture", "fixture_path": str(fixture)}],
        default_access_method_id="fixture",
        operational_profile_ids=["local-development-usable.v1"],
    )
    profiles = OperationalProfileRegistry()
    profiles.load_directory(repo_root / "profiles")
    return environment, EnvironmentIntelligenceService().collect(environment, profiles=[profiles.get("local-development-usable.v1")])


def _registries(repo_root: Path):
    lifecycle = LifecycleProfileRegistry()
    lifecycle.load_directory(repo_root / "lifecycle")
    policies = ExecutionPolicyRegistry()
    policies.load_directory(repo_root / "policies")
    return lifecycle, policies


def test_lifecycle_plan_compiles_dependency_aware_actions(repo_root: Path) -> None:
    environment, result = _snapshot(repo_root)
    lifecycle, _ = _registries(repo_root)
    assessment = next(item for item in result.assessments if item.profile_id == "local-development-usable.v1")
    plan = LifecyclePlanner(build_builtin_action_catalog()).plan(
        lifecycle.get("local-development-startup.v1"),
        result.snapshot,
        assessment,
        mode="dry_run",
    )
    assert plan.environment_id == environment.environment_id
    assert plan.operation_type == "startup"
    assert [item.stage_id for item in plan.actions] == ["platform", "workloads"]
    assert plan.actions[1].depends_on_action_ids == [plan.actions[0].action_id]
    assert plan.actions[1].parameters == {"kind": "deployment", "name": "web", "namespace": "demo"}
    assert plan.actions[1].risk.risk_class == "R2"


def test_policy_separates_capability_approval_and_target_fingerprint(repo_root: Path) -> None:
    environment, result = _snapshot(repo_root)
    lifecycle, policies = _registries(repo_root)
    plan = LifecyclePlanner(build_builtin_action_catalog()).plan(
        lifecycle.get("local-development-startup.v1"), result.snapshot, mode="guarded_execution"
    )
    action = plan.actions[-1]
    definition = build_builtin_action_catalog().get(action.action_type_id)
    policy = policies.get("local-development-guarded.v1")
    base = PolicyContext(
        environment_class="development",
        environment_fingerprint="actual",
        expected_fingerprint="expected",
        capabilities=frozenset(),
    )
    denied = PolicyEngine().evaluate(action, definition, policy, base)
    assert denied.outcome == "deny"
    assert denied.capability_gaps
    assert any("fingerprint" in item for item in denied.reasons)

    approved_context = PolicyContext(
        environment_class="development",
        environment_fingerprint="same",
        expected_fingerprint="same",
        capabilities=frozenset({"kubernetes.workload.restart"}),
    )
    pending = PolicyEngine().evaluate(action, definition, policy, approved_context)
    assert pending.outcome == "approval_required"
    approval = ApprovalRecord(
        approval_id="approval-1",
        operation_id="op",
        action_id=action.action_id,
        approver_id="operator",
        decision="approve",
        granted_at_iso=utc_now_iso(),
    )
    allowed = PolicyEngine().evaluate(action, definition, policy, approved_context, [approval])
    assert allowed.outcome == "allow"
    assert allowed.requires_checkpoint is True


def test_dry_run_journals_actions_without_mutation(repo_root: Path, tmp_path: Path) -> None:
    environment, result = _snapshot(repo_root)
    lifecycle, policies = _registries(repo_root)
    actions = build_builtin_action_catalog()
    plan = LifecyclePlanner(actions).plan(lifecycle.get("local-development-startup.v1"), result.snapshot, mode="dry_run")
    store = FileOperationStore(tmp_path / "operations")
    runtime = OperationRuntime(actions, build_default_executor_registry(), store)
    operation = runtime.create(environment.environment_id, plan, mode="dry_run")
    context = RuntimeContext(
        policy_context=PolicyContext(
            environment_class="development",
            environment_fingerprint="same",
            expected_fingerprint="same",
            capabilities=frozenset({"argocd.application.refresh", "kubernetes.workload.restart"}),
        ),
        execution_context=ExecutionContext(operation_id=operation.operation_id, mode="fixture", environment_id=environment.environment_id),
        world_provider=lambda: {item.entity_id: item.observed_state for item in result.snapshot.entities},
        relationships_provider=lambda: result.snapshot.relationships,
    )
    # Approval action id must match the operation's immutable plan.
    approval = ApprovalRecord(
        approval_id="approval-1", operation_id=operation.operation_id, action_id=plan.actions[-1].action_id,
        approver_id="operator", decision="approve", granted_at_iso=utc_now_iso(),
    )
    operation = runtime.add_approval(operation, approval)
    finished = runtime.run(operation, policies.get("local-development-guarded.v1"), context)
    assert finished.status == "completed"
    assert len(finished.action_receipts) == 2
    assert {item.executor_id for item in finished.action_receipts} == {"dry_run"}
    assert finished.checkpoints
    assert finished.recovery_certificate is not None
    assert finished.recovery_certificate.status == "partially_recovered"
    assert not finished.current_action_ids
    assert all(item.status == "skipped" for item in finished.plan.actions)
    assert sum(item.event_type == "action.started" for item in finished.events) == 2
    assert store.load(operation.operation_id).content_hash == finished.content_hash


def test_simulated_execution_is_idempotent_and_verifies(repo_root: Path, tmp_path: Path) -> None:
    environment, result = _snapshot(repo_root)
    lifecycle, policies = _registries(repo_root)
    actions = build_builtin_action_catalog()
    plan = LifecyclePlanner(actions).plan(lifecycle.get("local-development-startup.v1"), result.snapshot, mode="guarded_execution")
    # Avoid real commands and let both actions update a simulated readiness target.
    rewritten = []
    for item in plan.actions:
        rewritten.append(item.model_copy(update={"parameters": {**item.parameters, "simulation_effects": [{"entity_id": "target", "path": "ready", "value": True}]}}))
    # Append a second action with the same idempotency key to prove suppression.
    duplicate = rewritten[-1].model_copy(update={"action_id": "action:duplicate", "depends_on_action_ids": [rewritten[-1].action_id]})
    plan = plan.model_copy(update={"actions": [*rewritten, duplicate]})
    store = FileOperationStore(tmp_path / "operations")
    runtime = OperationRuntime(actions, build_default_executor_registry(), store)
    operation = runtime.create(environment.environment_id, plan, mode="guarded_execution")
    approval = ApprovalRecord(approval_id="approval", operation_id=operation.operation_id, action_id=None, approver_id="operator", decision="approve", granted_at_iso=utc_now_iso())
    operation = runtime.add_approval(operation, approval)
    world = {"target": {"ready": False}}
    context = RuntimeContext(
        policy_context=PolicyContext(
            environment_class="development", environment_fingerprint="same", expected_fingerprint="same",
            capabilities=frozenset({"argocd.application.refresh", "kubernetes.workload.restart"}),
        ),
        execution_context=ExecutionContext(operation_id=operation.operation_id, mode="simulation", environment_id=environment.environment_id, simulation_world=world),
        world_provider=lambda: world,
    )
    condition = VerificationCondition(
        condition_id="target.ready", title="Target is ready",
        predicate=FieldEquals(entity_id="target", path="ready", value=True), level="semantic_health",
    )
    finished = runtime.run(operation, policies.get("local-development-guarded.v1"), context, [condition])
    assert finished.status == "completed"
    assert finished.action_receipts[-1].status == "already_satisfied"
    assert finished.verification_results[0].status == "healthy"
    assert finished.recovery_certificate and finished.recovery_certificate.status == "partially_recovered"


class FailingRunner(CommandRunner):
    def run(self, argv, *, cwd, env, timeout):
        import subprocess
        if argv[:2] == ["systemctl", "restart"]:
            return subprocess.CompletedProcess(argv, 9, "", "intentional failure")
        return subprocess.CompletedProcess(argv, 0, "ok", "")


def test_failure_rolls_back_reversible_completed_actions(repo_root: Path, tmp_path: Path) -> None:
    actions = build_builtin_action_catalog()
    first = actions.get("docker.container.start.v1").default_risk
    second = actions.get("host.service.restart.v1").default_risk
    from kubeops_core.models import ActionInstance
    plan = RecoveryPlan(
        plan_id="plan:rollback", environment_id="dev", operation_type="recovery", objective_id="restore",
        actions=[
            ActionInstance(action_id="start", action_type_id="docker.container.start.v1", parameters={"container": "kind-control-plane"}, risk=first, idempotency_key="container:start"),
            ActionInstance(action_id="fail", action_type_id="host.service.restart.v1", parameters={"service": "k3s"}, risk=second, depends_on_action_ids=["start"]),
        ], mode="guarded_execution", policy_id="custom",
    )
    policy = ExecutionPolicy(
        policy_id="custom", title="custom", environment_classes={"development"},
        allowed_risk_classes={"R1", "R2"}, allowed_action_type_ids={item.action_type_id for item in plan.actions},
        required_approvals_by_risk={"R2": 0}, require_target_fingerprint=False,
        capability_grants={"docker.container.start", "docker.container.stop", "host.service.restart"},
    )
    executors = build_default_executor_registry(FailingRunner())
    runtime = OperationRuntime(actions, executors, FileOperationStore(tmp_path / "ops"))
    operation = runtime.create("dev", plan, mode="guarded_execution")
    context = RuntimeContext(
        policy_context=PolicyContext(environment_class="development"),
        execution_context=ExecutionContext(operation_id=operation.operation_id, mode="live", environment_id="dev"),
        world_provider=lambda: {},
    )
    finished = runtime.run(operation, policy, context)
    assert finished.status == "failed"
    assert finished.recovery_certificate and finished.recovery_certificate.status == "rollback_completed"
    # Both the initial start and its rollback fail with this runner, but the rollback attempt is preserved.
    assert any(item.action_id.startswith("rollback:") for item in finished.action_receipts)
    assert any(item.event_type == "action.rolled_back" for item in finished.events)

class SequenceRunner(CommandRunner):
    def __init__(self, results):
        self.results = list(results)
        self.argv = []

    def run(self, argv, *, cwd, env, timeout):
        self.argv.append(argv)
        return self.results.pop(0)


def test_terminal_job_deletion_treats_not_found_as_idempotent_success(tmp_path: Path) -> None:
    import subprocess
    from kubeops_core.models import ActionInstance
    actions = build_builtin_action_catalog()
    action = ActionInstance(
        action_id="cleanup", action_type_id="kubernetes.job.delete_terminal.v1",
        parameters={"name": "worker-1", "namespace": "builder", "require_terminal": True},
        risk=actions.get("kubernetes.job.delete_terminal.v1").default_risk,
    )
    runner = SequenceRunner([subprocess.CompletedProcess([], 1, "", 'Error from server (NotFound): jobs "worker-1" not found')])
    executor = build_default_executor_registry(runner).get("kubectl.safe")
    receipt = executor.execute(action, actions.get(action.action_type_id), ExecutionContext(operation_id="op", mode="live", environment_id="dev"), 1)
    assert receipt.status == "already_satisfied"
    assert receipt.observed_effects == ["job_absent"]
    assert receipt.metadata["not_found_is_success"] is True
    assert len(runner.argv) == 1


def test_terminal_job_deletion_refuses_active_job() -> None:
    import subprocess
    from kubeops_core.models import ActionInstance
    actions = build_builtin_action_catalog()
    action = ActionInstance(
        action_id="cleanup", action_type_id="kubernetes.job.delete_terminal.v1",
        parameters={"name": "worker-1", "namespace": "builder", "require_terminal": True},
        risk=actions.get("kubernetes.job.delete_terminal.v1").default_risk,
    )
    runner = SequenceRunner([subprocess.CompletedProcess([], 0, '{"status":{"active":1}}', "")])
    executor = build_default_executor_registry(runner).get("kubectl.safe")
    receipt = executor.execute(action, actions.get(action.action_type_id), ExecutionContext(operation_id="op", mode="live", environment_id="dev"), 1)
    assert receipt.status == "failed"
    assert "non-terminal" in receipt.stderr
    assert len(runner.argv) == 1


def test_policy_requires_distinct_unexpired_approvers_and_honors_rejection(repo_root: Path) -> None:
    from datetime import datetime, timedelta, timezone

    _, result = _snapshot(repo_root)
    lifecycle, _ = _registries(repo_root)
    actions = build_builtin_action_catalog()
    plan = LifecyclePlanner(actions).plan(
        lifecycle.get("local-development-startup.v1"), result.snapshot, mode="guarded_execution"
    )
    action = plan.actions[-1]
    definition = actions.get(action.action_type_id)
    policy = ExecutionPolicy(
        policy_id="two-person",
        title="Two-person approval",
        environment_classes={"development"},
        allowed_risk_classes={"R2"},
        allowed_action_type_ids={action.action_type_id},
        required_approvals_by_risk={"R2": 2},
        require_target_fingerprint=False,
        capability_grants=set(definition.required_capabilities),
    )
    now = datetime.now(timezone.utc)
    duplicate = [
        ApprovalRecord(
            approval_id=f"same-{index}", operation_id="op", action_id=action.action_id,
            approver_id="same-operator", decision="approve", granted_at_iso=now.isoformat(),
        )
        for index in range(2)
    ]
    pending = PolicyEngine().evaluate(action, definition, policy, PolicyContext(environment_class="development"), duplicate)
    assert pending.outcome == "approval_required"
    assert "distinct" in " ".join(pending.reasons)

    expired = ApprovalRecord(
        approval_id="expired", operation_id="op", action_id=action.action_id,
        approver_id="second", decision="approve", granted_at_iso=(now - timedelta(hours=2)).isoformat(),
        expires_at_iso=(now - timedelta(hours=1)).isoformat(),
    )
    still_pending = PolicyEngine().evaluate(
        action, definition, policy, PolicyContext(environment_class="development"), [duplicate[0], expired]
    )
    assert still_pending.outcome == "approval_required"

    reject = ApprovalRecord(
        approval_id="reject", operation_id="op", action_id=action.action_id,
        approver_id="security", decision="reject", granted_at_iso=now.isoformat(),
    )
    denied = PolicyEngine().evaluate(
        action, definition, policy, PolicyContext(environment_class="development"), [*duplicate, reject]
    )
    assert denied.outcome == "deny"
    assert any("rejected" in reason for reason in denied.reasons)


def test_lifecycle_profile_rejects_stage_and_template_cycles() -> None:
    import pytest
    from kubeops_core.models import LifecycleProfile

    with pytest.raises(ValueError, match="lifecycle stage graph must be acyclic"):
        LifecycleProfile(
            profile_id="cyclic", title="cyclic", operation_type="startup",
            target_operational_profile_id="healthy",
            stages=[
                {"stage_id": "one", "title": "one", "depends_on_stage_ids": ["two"]},
                {"stage_id": "two", "title": "two", "depends_on_stage_ids": ["one"]},
            ],
        )

    with pytest.raises(ValueError, match="action-template graph"):
        LifecycleProfile(
            profile_id="template-cycle", title="template cycle", operation_type="startup",
            target_operational_profile_id="healthy",
            stages=[{
                "stage_id": "one", "title": "one",
                "action_templates": [
                    {"template_id": "a", "action_type_id": "operation.wait_for_condition.v1", "title": "a", "depends_on_template_ids": ["b"]},
                    {"template_id": "b", "action_type_id": "operation.wait_for_condition.v1", "title": "b", "depends_on_template_ids": ["a"]},
                ],
            }],
        )


def test_operation_artifacts_form_content_addressed_lineage(repo_root: Path, tmp_path: Path) -> None:
    from kubeops_core.artifacts import build_operation_artifacts

    environment, result = _snapshot(repo_root)
    lifecycle, _ = _registries(repo_root)
    actions = build_builtin_action_catalog()
    plan = LifecyclePlanner(actions).plan(
        lifecycle.get("local-development-startup.v1"), result.snapshot, mode="dry_run"
    )
    runtime = OperationRuntime(actions, build_default_executor_registry(), FileOperationStore(tmp_path / "operations"))
    operation = runtime.create(environment.environment_id, plan, mode="dry_run")
    artifacts = build_operation_artifacts(operation)
    assert artifacts[-1].artifact_type == "operation_manifest"
    assert artifacts[-1].derived_from == [item.artifact_id for item in artifacts[:-1]]
    assert len({item.artifact_id for item in artifacts}) == len(artifacts)
    repeated = build_operation_artifacts(operation)
    assert [item.artifact_id for item in repeated] == [item.artifact_id for item in artifacts]
    assert all(item.payload_hash != "pending" for item in artifacts)


def test_operation_creation_rejects_invalid_action_parameters(tmp_path: Path) -> None:
    import pytest
    from kubeops_core.models import ActionInstance

    actions = build_builtin_action_catalog()
    plan = RecoveryPlan(
        plan_id="plan:invalid-parameters", environment_id="dev", operation_type="recovery", objective_id="restore",
        actions=[ActionInstance(
            action_id="restart", action_type_id="kubernetes.workload.rollout_restart.v1",
            parameters={"kind": "deployment", "namespace": "demo"},
            risk=actions.get("kubernetes.workload.rollout_restart.v1").default_risk,
        )],
    )
    runtime = OperationRuntime(actions, build_default_executor_registry(), FileOperationStore(tmp_path / "ops"))
    with pytest.raises(ValueError, match="missing required parameters"):
        runtime.create("dev", plan)


def test_policy_denies_action_in_unsupported_execution_mode() -> None:
    from kubeops_core.models import ActionInstance

    actions = build_builtin_action_catalog()
    definition = actions.get("docker.container.start.v1")
    action = ActionInstance(
        action_id="start", action_type_id=definition.action_type_id,
        parameters={"container": "kind-control-plane"}, risk=definition.default_risk,
    )
    policy = ExecutionPolicy(
        policy_id="fixture", title="fixture", environment_classes={"development"},
        allowed_risk_classes={"R1"}, allowed_action_type_ids={definition.action_type_id},
        require_target_fingerprint=False, capability_grants=set(definition.required_capabilities),
    )
    decision = PolicyEngine().evaluate(
        action, definition, policy,
        PolicyContext(environment_class="development", execution_mode="fixture"),
    )
    assert decision.outcome == "deny"
    assert any("execution mode" in reason for reason in decision.reasons)


def test_release_04_registry_categories_accept_actions_lifecycle_and_policy() -> None:
    from kubeops_core.models.registry import RegistryEntry

    for category in ["action_type", "lifecycle_profile", "execution_policy"]:
        entry = RegistryEntry(registry_key=f"test:{category}", category=category, title=category)  # type: ignore[arg-type]
        assert entry.category == category


def test_release_04_registries_preserve_source_provenance(repo_root: Path) -> None:
    lifecycle, policies = _registries(repo_root)
    assert lifecycle.source("local-development-startup.v1").endswith(
        "lifecycle/local-development-startup.v1.yaml"
    )
    assert policies.source("local-development-guarded.v1").endswith(
        "policies/local-development-guarded.v1.yaml"
    )


def test_operation_can_be_durably_cancelled(repo_root: Path, tmp_path: Path) -> None:
    environment, result = _snapshot(repo_root)
    lifecycle, _ = _registries(repo_root)
    actions = build_builtin_action_catalog()
    plan = LifecyclePlanner(actions).plan(
        lifecycle.get("local-development-startup.v1"), result.snapshot, mode="dry_run"
    )
    store = FileOperationStore(tmp_path / "ops")
    runtime = OperationRuntime(actions, build_default_executor_registry(), store)
    operation = runtime.create(environment.environment_id, plan, mode="dry_run")
    cancelled = runtime.cancel(operation, "operator aborted")
    assert cancelled.status == "cancelled"
    assert cancelled.failure_reason == "operator aborted"
    assert cancelled.events[-1].event_type == "operation.cancelled"
    assert store.load(cancelled.operation_id).status == "cancelled"


def test_stage_pause_failure_semantics_are_preserved(repo_root: Path, tmp_path: Path) -> None:
    import subprocess
    from kubeops_core.models import ActionInstance

    actions = build_builtin_action_catalog()
    definition = actions.get("host.service.restart.v1")
    plan = RecoveryPlan(
        plan_id="plan:pause-on-failure",
        environment_id="dev",
        operation_type="recovery",
        objective_id="restore",
        actions=[
            ActionInstance(
                action_id="restart",
                action_type_id=definition.action_type_id,
                parameters={"service": "k3s"},
                risk=definition.default_risk,
                metadata={"on_failure": "pause"},
            )
        ],
        mode="guarded_execution",
    )
    policy = ExecutionPolicy(
        policy_id="pause",
        title="pause",
        environment_classes={"development"},
        allowed_risk_classes={"R2"},
        allowed_action_type_ids={definition.action_type_id},
        require_target_fingerprint=False,
        capability_grants=set(definition.required_capabilities),
    )
    runner = SequenceRunner([subprocess.CompletedProcess([], 1, "", "failed")])
    runtime = OperationRuntime(
        actions,
        build_default_executor_registry(runner),
        FileOperationStore(tmp_path / "pause-ops"),
    )
    operation = runtime.create("dev", plan, mode="guarded_execution")
    context = RuntimeContext(
        policy_context=PolicyContext(environment_class="development", execution_mode="live"),
        execution_context=ExecutionContext(operation_id=operation.operation_id, mode="live", environment_id="dev"),
        world_provider=lambda: {},
    )
    paused = runtime.run(operation, policy, context)
    assert paused.status == "paused"
    assert paused.pause_reason == "action restart failed"
    assert paused.events[-1].event_type == "operation.paused"
