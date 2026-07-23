from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from kubeops_core.models.operation import ActionReceipt
from kubeops_core.models.planning import ActionInstance, ActionTypeDefinition
from kubeops_core.util import utc_now_iso


@dataclass
class ExecutionContext:
    operation_id: str
    mode: str
    environment_id: str
    working_directory: Path | None = None
    environment: dict[str, str] = field(default_factory=dict)
    executable_allowlist: set[str] = field(default_factory=lambda: {"docker", "kubectl", "systemctl", "service", "kill"})
    command_timeout_seconds: int = 120
    simulation_world: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ActionExecutor(Protocol):
    executor_id: str

    def execute(self, action: ActionInstance, definition: ActionTypeDefinition, context: ExecutionContext, attempt: int) -> ActionReceipt: ...


class ExecutorRegistry:
    def __init__(self) -> None:
        self._items: dict[str, ActionExecutor] = {}

    def register(self, executor: ActionExecutor) -> None:
        if executor.executor_id in self._items:
            raise ValueError(f"executor {executor.executor_id!r} is already registered")
        self._items[executor.executor_id] = executor

    def get(self, executor_id: str) -> ActionExecutor:
        try:
            return self._items[executor_id]
        except KeyError as exc:
            raise KeyError(f"unknown executor {executor_id!r}") from exc


class SimulationExecutor:
    executor_id = "simulation"

    def execute(self, action: ActionInstance, definition: ActionTypeDefinition, context: ExecutionContext, attempt: int) -> ActionReceipt:
        started = utc_now_iso()
        effects = list(action.parameters.get("simulation_effects", []))
        if not effects and action.target_ids:
            target_id = action.target_ids[0]
            current = context.simulation_world.setdefault(target_id, {})
            if action.action_type_id == "kubernetes.workload.rollout_restart.v1":
                desired = current.get("observed_state", {}).get("desired_replicas", current.get("desired_state", {}).get("replicas", 1))
                effects = [
                    {"entity_id": target_id, "path": "observed_state.ready_replicas", "value": desired},
                    {"entity_id": target_id, "path": "observed_state.available_replicas", "value": desired},
                ]
            elif action.action_type_id == "docker.container.stop.v1":
                effects = [{"entity_id": target_id, "path": "observed_state.ready", "value": False}]
            elif action.action_type_id == "docker.container.start.v1":
                effects = [{"entity_id": target_id, "path": "observed_state.ready", "value": True}]
            elif action.action_type_id == "kubernetes.job.delete_terminal.v1":
                context.simulation_world.pop(target_id, None)
        for effect in effects:
            target = context.simulation_world.setdefault(effect["entity_id"], {})
            path = effect.get("path", "status")
            parts = path.split(".")
            cursor = target
            for part in parts[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor[parts[-1]] = effect.get("value")
        completed = utc_now_iso()
        return ActionReceipt(
            receipt_id=f"receipt:{context.operation_id}:{action.action_id}:{attempt}",
            operation_id=context.operation_id,
            action_id=action.action_id,
            action_type_id=action.action_type_id,
            executor_id=self.executor_id,
            status="completed",
            attempt=attempt,
            started_at_iso=started,
            completed_at_iso=completed,
            stdout="simulated action completed",
            observed_effects=definition.expected_effects,
            idempotency_key=action.idempotency_key,
            metadata={"simulated": True},
        )


class DryRunExecutor:
    executor_id = "dry_run"

    def execute(self, action: ActionInstance, definition: ActionTypeDefinition, context: ExecutionContext, attempt: int) -> ActionReceipt:
        now = utc_now_iso()
        return ActionReceipt(
            receipt_id=f"receipt:{context.operation_id}:{action.action_id}:dry-run",
            operation_id=context.operation_id,
            action_id=action.action_id,
            action_type_id=action.action_type_id,
            executor_id=self.executor_id,
            status="skipped",
            attempt=attempt,
            started_at_iso=now,
            completed_at_iso=now,
            stdout="dry run: no mutation executed",
            observed_effects=[],
            idempotency_key=action.idempotency_key,
            metadata={"dry_run": True, "would_execute_with": definition.executor_id},
        )


class WaitExecutor:
    executor_id = "builtin.wait"

    def execute(self, action: ActionInstance, definition: ActionTypeDefinition, context: ExecutionContext, attempt: int) -> ActionReceipt:
        now = utc_now_iso()
        satisfied = bool(action.parameters.get("condition_satisfied", False))
        return ActionReceipt(
            receipt_id=f"receipt:{context.operation_id}:{action.action_id}:{attempt}",
            operation_id=context.operation_id, action_id=action.action_id, action_type_id=action.action_type_id,
            executor_id=self.executor_id, status="completed" if satisfied else "failed", attempt=attempt,
            started_at_iso=now, completed_at_iso=now,
            stdout="condition satisfied" if satisfied else "condition not yet satisfied",
            observed_effects=definition.expected_effects if satisfied else [], idempotency_key=action.idempotency_key,
        )


class PortForwardExecutor:
    executor_id = "port_forward"

    def execute(self, action: ActionInstance, definition: ActionTypeDefinition, context: ExecutionContext, attempt: int) -> ActionReceipt:
        started = utc_now_iso()
        namespace = str(action.parameters["namespace"])
        resource = str(action.parameters["resource"])
        local_port = int(action.parameters["local_port"])
        remote_port = int(action.parameters["remote_port"])
        argv = ["kubectl", "-n", namespace, "port-forward", resource, f"{local_port}:{remote_port}"]
        if "kubectl" not in context.executable_allowlist:
            raise PermissionError("kubectl is outside the execution allowlist")
        process = subprocess.Popen(argv, cwd=str(context.working_directory) if context.working_directory else None, env={**os.environ, **context.environment}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        ended = utc_now_iso()
        return ActionReceipt(
            receipt_id=f"receipt:{context.operation_id}:{action.action_id}:{attempt}", operation_id=context.operation_id,
            action_id=action.action_id, action_type_id=action.action_type_id, executor_id=self.executor_id, status="completed",
            attempt=attempt, started_at_iso=started, completed_at_iso=ended, stdout=f"started pid {process.pid}",
            observed_effects=definition.expected_effects, idempotency_key=action.idempotency_key, metadata={"argv": argv, "pid": process.pid},
        )


class CommandRunner:
    def run(self, argv: list[str], *, cwd: Path | None, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )


class SafeCommandExecutor:
    def __init__(self, executor_id: str, builder: Callable[[ActionInstance], list[str]], runner: CommandRunner | None = None) -> None:
        self.executor_id = executor_id
        self.builder = builder
        self.runner = runner or CommandRunner()

    def execute(self, action: ActionInstance, definition: ActionTypeDefinition, context: ExecutionContext, attempt: int) -> ActionReceipt:
        started = utc_now_iso()
        argv = self.builder(action)
        executable = Path(argv[0]).name
        if executable not in context.executable_allowlist:
            raise PermissionError(f"executable {executable!r} is outside the execution allowlist")
        try:
            completed = self.runner.run(
                argv,
                cwd=context.working_directory,
                env=context.environment,
                timeout=min(definition.timeout_seconds, context.command_timeout_seconds),
            )
            status = "completed" if completed.returncode == 0 else "failed"
            stderr = completed.stderr
            observed = definition.expected_effects if completed.returncode == 0 else []
        except subprocess.TimeoutExpired as exc:
            completed = None
            status = "failed"
            stderr = f"command timed out after {exc.timeout}s"
            observed = []
        ended = utc_now_iso()
        return ActionReceipt(
            receipt_id=f"receipt:{context.operation_id}:{action.action_id}:{attempt}",
            operation_id=context.operation_id,
            action_id=action.action_id,
            action_type_id=action.action_type_id,
            executor_id=self.executor_id,
            status=status,  # type: ignore[arg-type]
            attempt=attempt,
            started_at_iso=started,
            completed_at_iso=ended,
            exit_code=completed.returncode if completed else None,
            stdout=completed.stdout if completed else "",
            stderr=stderr,
            observed_effects=observed,
            idempotency_key=action.idempotency_key,
            metadata={"argv": argv},
        )


def _docker_builder(action: ActionInstance) -> list[str]:
    container = str(action.parameters["container"])
    verb = "start" if action.action_type_id.endswith("start.v1") else "stop"
    return ["docker", verb, container]


def _service_builder(action: ActionInstance) -> list[str]:
    service = str(action.parameters["service"])
    return ["systemctl", "restart", service]


def _kubectl_builder(action: ActionInstance) -> list[str]:
    namespace = str(action.parameters.get("namespace", "default"))
    context = action.parameters.get("context")
    prefix = ["kubectl"]
    if context:
        prefix += ["--context", str(context)]
    prefix += ["-n", namespace]
    if action.action_type_id == "kubernetes.workload.rollout_restart.v1":
        kind = str(action.parameters["kind"]).lower()
        name = str(action.parameters["name"])
        if kind not in {"deployment", "statefulset", "daemonset"}:
            raise ValueError(f"rollout restart does not allow kind {kind!r}")
        return [*prefix, "rollout", "restart", f"{kind}/{name}"]
    if action.action_type_id == "kubernetes.job.delete_terminal.v1":
        if action.parameters.get("require_terminal") is not True:
            raise ValueError("terminal Job deletion requires require_terminal=true")
        return [*prefix, "delete", "job", str(action.parameters["name"]), "--ignore-not-found=true", "--wait=true"]
    if action.action_type_id == "argocd.application.refresh.v1":
        return [*prefix, "annotate", "application.argoproj.io", str(action.parameters["name"]), "argocd.argoproj.io/refresh=normal", "--overwrite"]
    raise ValueError(f"unsupported kubectl action {action.action_type_id!r}")


def _local_process_builder(action: ActionInstance) -> list[str]:
    argv = action.parameters.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        raise ValueError("local process action requires a non-empty string argv list")
    if action.action_type_id == "local.process.stop.v1":
        pid = action.parameters.get("pid")
        if pid is None:
            raise ValueError("tracked process stop requires pid")
        return ["kill", "-TERM", str(int(pid))]
    return argv



class LocalProcessExecutor:
    executor_id = "local.process"

    def execute(self, action: ActionInstance, definition: ActionTypeDefinition, context: ExecutionContext, attempt: int) -> ActionReceipt:
        started = utc_now_iso()
        if action.action_type_id == "local.process.stop.v1":
            pid = int(action.parameters["pid"])
            try:
                os.kill(pid, 15)
                status = "completed"
                message = f"sent SIGTERM to pid {pid}"
            except ProcessLookupError:
                status = "already_satisfied"
                message = f"pid {pid} is already absent"
            ended = utc_now_iso()
            return ActionReceipt(
                receipt_id=f"receipt:{context.operation_id}:{action.action_id}:{attempt}", operation_id=context.operation_id,
                action_id=action.action_id, action_type_id=action.action_type_id, executor_id=self.executor_id,
                status=status, attempt=attempt, started_at_iso=started, completed_at_iso=ended, stdout=message,
                observed_effects=definition.expected_effects, idempotency_key=action.idempotency_key, metadata={"pid": pid},
            )
        argv = action.parameters.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
            raise ValueError("local process start requires a non-empty string argv list")
        executable = Path(argv[0]).name
        if executable not in context.executable_allowlist:
            raise PermissionError(f"executable {executable!r} is outside the execution allowlist")
        process = subprocess.Popen(
            argv, cwd=str(context.working_directory) if context.working_directory else None,
            env={**os.environ, **context.environment}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        ended = utc_now_iso()
        return ActionReceipt(
            receipt_id=f"receipt:{context.operation_id}:{action.action_id}:{attempt}", operation_id=context.operation_id,
            action_id=action.action_id, action_type_id=action.action_type_id, executor_id=self.executor_id,
            status="completed", attempt=attempt, started_at_iso=started, completed_at_iso=ended,
            stdout=f"started pid {process.pid}", observed_effects=definition.expected_effects,
            idempotency_key=action.idempotency_key, metadata={"argv": argv, "pid": process.pid},
        )


class KubectlSafeExecutor:
    executor_id = "kubectl.safe"

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def execute(self, action: ActionInstance, definition: ActionTypeDefinition, context: ExecutionContext, attempt: int) -> ActionReceipt:
        if "kubectl" not in context.executable_allowlist:
            raise PermissionError("kubectl is outside the execution allowlist")
        started = utc_now_iso()
        if action.action_type_id == "kubernetes.job.delete_terminal.v1":
            return self._delete_terminal_job(action, definition, context, attempt, started)
        argv = _kubectl_builder(action)
        completed = self.runner.run(argv, cwd=context.working_directory, env=context.environment, timeout=min(definition.timeout_seconds, context.command_timeout_seconds))
        ended = utc_now_iso()
        ok = completed.returncode == 0
        return ActionReceipt(
            receipt_id=f"receipt:{context.operation_id}:{action.action_id}:{attempt}", operation_id=context.operation_id,
            action_id=action.action_id, action_type_id=action.action_type_id, executor_id=self.executor_id,
            status="completed" if ok else "failed", attempt=attempt, started_at_iso=started, completed_at_iso=ended,
            exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr,
            observed_effects=definition.expected_effects if ok else [], idempotency_key=action.idempotency_key,
            metadata={"argv": argv},
        )

    def _delete_terminal_job(self, action: ActionInstance, definition: ActionTypeDefinition, context: ExecutionContext, attempt: int, started: str) -> ActionReceipt:
        namespace = str(action.parameters.get("namespace", "default"))
        name = str(action.parameters["name"])
        context_name = action.parameters.get("context")
        prefix = ["kubectl"] + (["--context", str(context_name)] if context_name else []) + ["-n", namespace]
        get_argv = [*prefix, "get", "job", name, "-o", "json"]
        current = self.runner.run(get_argv, cwd=context.working_directory, env=context.environment, timeout=min(definition.timeout_seconds, context.command_timeout_seconds))
        ended = utc_now_iso()
        if current.returncode != 0 and ("NotFound" in current.stderr or "not found" in current.stderr.lower()):
            return ActionReceipt(
                receipt_id=f"receipt:{context.operation_id}:{action.action_id}:{attempt}", operation_id=context.operation_id,
                action_id=action.action_id, action_type_id=action.action_type_id, executor_id=self.executor_id,
                status="already_satisfied", attempt=attempt, started_at_iso=started, completed_at_iso=ended,
                exit_code=current.returncode, stdout="job is already absent", stderr=current.stderr,
                observed_effects=["job_absent"], idempotency_key=action.idempotency_key,
                metadata={"preflight_argv": get_argv, "not_found_is_success": True},
            )
        if current.returncode != 0:
            return ActionReceipt(
                receipt_id=f"receipt:{context.operation_id}:{action.action_id}:{attempt}", operation_id=context.operation_id,
                action_id=action.action_id, action_type_id=action.action_type_id, executor_id=self.executor_id,
                status="failed", attempt=attempt, started_at_iso=started, completed_at_iso=ended,
                exit_code=current.returncode, stderr=current.stderr, idempotency_key=action.idempotency_key,
                metadata={"preflight_argv": get_argv},
            )
        try:
            payload = json.loads(current.stdout)
        except json.JSONDecodeError:
            payload = {}
        status_payload = payload.get("status", {})
        conditions = status_payload.get("conditions", [])
        terminal = bool(status_payload.get("completionTime") or status_payload.get("succeeded") or status_payload.get("failed")) or any(
            item.get("type") in {"Complete", "Failed"} and str(item.get("status")).lower() == "true" for item in conditions
        )
        if not terminal:
            return ActionReceipt(
                receipt_id=f"receipt:{context.operation_id}:{action.action_id}:{attempt}", operation_id=context.operation_id,
                action_id=action.action_id, action_type_id=action.action_type_id, executor_id=self.executor_id,
                status="failed", attempt=attempt, started_at_iso=started, completed_at_iso=ended,
                stderr="refused to delete a non-terminal Job", idempotency_key=action.idempotency_key,
                metadata={"preflight_argv": get_argv, "terminal": False},
            )
        delete_argv = [*prefix, "delete", "job", name, "--ignore-not-found=true", "--wait=true"]
        deleted = self.runner.run(delete_argv, cwd=context.working_directory, env=context.environment, timeout=min(definition.timeout_seconds, context.command_timeout_seconds))
        ended = utc_now_iso()
        ok = deleted.returncode == 0 or "NotFound" in deleted.stderr
        return ActionReceipt(
            receipt_id=f"receipt:{context.operation_id}:{action.action_id}:{attempt}", operation_id=context.operation_id,
            action_id=action.action_id, action_type_id=action.action_type_id, executor_id=self.executor_id,
            status="completed" if ok else "failed", attempt=attempt, started_at_iso=started, completed_at_iso=ended,
            exit_code=deleted.returncode, stdout=deleted.stdout, stderr=deleted.stderr,
            observed_effects=["job_absent"] if ok else [], idempotency_key=action.idempotency_key,
            metadata={"preflight_argv": get_argv, "argv": delete_argv, "terminal": True},
        )


def build_default_executor_registry(runner: CommandRunner | None = None) -> ExecutorRegistry:
    registry = ExecutorRegistry()
    registry.register(SimulationExecutor())
    registry.register(DryRunExecutor())
    registry.register(WaitExecutor())
    registry.register(PortForwardExecutor())
    registry.register(SafeCommandExecutor("docker.cli", _docker_builder, runner))
    registry.register(SafeCommandExecutor("host.service", _service_builder, runner))
    registry.register(KubectlSafeExecutor(runner))
    registry.register(LocalProcessExecutor())
    return registry
