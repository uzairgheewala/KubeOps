from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from kubeops_core.models.executor import (
    DispatchDecision,
    ExecutionTask,
    ExecutorAgentDefinition,
    ExecutorHeartbeat,
    TaskLease,
)


def _aware(value: datetime) -> datetime:
    """Normalize caller supplied instants to timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_iso(value: str) -> datetime:
    return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))


class DistributedDispatcher:
    """Deterministic capability-aware task dispatcher.

    The class is transport neutral. A control plane may persist its objects in a
    database and deliver leased tasks over polling, SSE, or a message broker.
    """

    def __init__(self) -> None:
        self.agents: dict[str, ExecutorAgentDefinition] = {}
        self.tasks: dict[str, ExecutionTask] = {}
        self.leases: dict[str, TaskLease] = {}

    def register_agent(self, agent: ExecutorAgentDefinition) -> None:
        existing = self.agents.get(agent.agent_id)
        if existing is not None:
            immutable_identity = (
                existing.organization_id,
                existing.workspace_id,
                existing.public_identity,
            )
            requested_identity = (
                agent.organization_id,
                agent.workspace_id,
                agent.public_identity,
            )
            if immutable_identity != requested_identity:
                raise ValueError(
                    f"agent {agent.agent_id!r} is already registered with a different tenant or public identity"
                )
        self.agents[agent.agent_id] = agent

    def heartbeat(self, heartbeat: ExecutorHeartbeat) -> ExecutorAgentDefinition:
        agent = self.agents[heartbeat.agent_id]
        metadata = dict(agent.metadata)
        metadata.update({
            "available_capacity": heartbeat.available_capacity,
            "active_task_ids": list(heartbeat.active_task_ids),
            "heartbeat_diagnostics": dict(heartbeat.diagnostics),
        })
        updated = agent.model_copy(update={
            "status": heartbeat.status,
            "last_heartbeat_at_iso": heartbeat.occurred_at_iso,
            "capabilities": set(agent.capabilities) | set(heartbeat.capabilities),
            "metadata": metadata,
        })
        self.agents[agent.agent_id] = updated
        return updated

    def enqueue(self, task: ExecutionTask) -> None:
        existing = self.tasks.get(task.task_id)
        if existing is not None:
            if existing.payload_hash != task.payload_hash:
                raise ValueError(f"task {task.task_id!r} already exists with different content")
            # Same identity and content is an idempotent enqueue. Never reset a
            # leased or terminal task back to queued with a stale caller copy.
            return
        self.tasks[task.task_id] = task

    def _active_count(self, agent_id: str, at: datetime) -> int:
        now = _aware(at)
        return sum(
            1 for lease in self.leases.values()
            if lease.agent_id == agent_id and lease.status == "active"
            and _parse_iso(lease.expires_at_iso) > now
        )

    def _available_capacity(self, agent: ExecutorAgentDefinition, at: datetime) -> int:
        configured = int(agent.metadata.get("available_capacity", agent.max_concurrency))
        remaining_by_concurrency = max(0, agent.max_concurrency - self._active_count(agent.agent_id, at))
        return max(0, min(configured, remaining_by_concurrency))

    def dispatch(self, task_id: str, *, at: datetime | None = None) -> tuple[DispatchDecision, TaskLease | None]:
        now = _aware(at or datetime.now(timezone.utc))
        task = self.tasks[task_id]
        if task.status != "queued":
            return DispatchDecision(
                decision_id=f"dispatch:{uuid4()}", task_id=task_id, outcome="rejected",
                candidate_agent_ids=[], reasons=[f"task is {task.status}, not queued"],
                evaluated_at_iso=now.isoformat(),
            ), None
        if task.not_before_iso and _parse_iso(task.not_before_iso) > now:
            return DispatchDecision(
                decision_id=f"dispatch:{uuid4()}", task_id=task_id, outcome="queued",
                candidate_agent_ids=[], reasons=["task not-before time has not elapsed"],
                evaluated_at_iso=now.isoformat(),
            ), None
        if task.deadline_iso and _parse_iso(task.deadline_iso) <= now:
            self.tasks[task_id] = task.model_copy(update={"status": "expired", "updated_at_iso": now.isoformat()})
            return DispatchDecision(
                decision_id=f"dispatch:{uuid4()}", task_id=task_id, outcome="rejected",
                candidate_agent_ids=[], reasons=["task deadline has elapsed"],
                evaluated_at_iso=now.isoformat(),
            ), None
        candidates: list[ExecutorAgentDefinition] = []
        reasons: list[str] = []
        for agent in self.agents.values():
            if agent.status != "online":
                continue
            if task.workspace_id != agent.workspace_id or task.organization_id != agent.organization_id:
                continue
            if agent.environment_ids and task.environment_id not in agent.environment_ids:
                continue
            if task.executor_id not in agent.supported_executor_ids:
                continue
            if not task.required_capabilities.issubset(agent.capabilities):
                continue
            if self._available_capacity(agent, now) <= 0:
                continue
            candidates.append(agent)
        candidates.sort(key=lambda item: (self._active_count(item.agent_id, now), item.agent_id))
        if not candidates:
            reasons.append("no online executor satisfies workspace, environment, capability, executor, and capacity requirements")
            return DispatchDecision(
                decision_id=f"dispatch:{uuid4()}", task_id=task_id, outcome="queued",
                candidate_agent_ids=[], reasons=reasons, evaluated_at_iso=now.isoformat(),
            ), None
        agent = candidates[0]
        lease = TaskLease(
            lease_id=f"lease:{uuid4()}", task_id=task_id, agent_id=agent.agent_id,
            acquired_at_iso=now.isoformat(), expires_at_iso=(now + timedelta(seconds=agent.lease_ttl_seconds)).isoformat(),
            heartbeat_at_iso=now.isoformat(), nonce=uuid4().hex,
        )
        self.leases[lease.lease_id] = lease
        self.tasks[task_id] = task.model_copy(update={"status": "leased", "assigned_agent_id": agent.agent_id, "updated_at_iso": now.isoformat()})
        return DispatchDecision(
            decision_id=f"dispatch:{uuid4()}", task_id=task_id, outcome="assigned",
            agent_id=agent.agent_id, candidate_agent_ids=[item.agent_id for item in candidates],
            reasons=["selected least-loaded compatible online executor"], evaluated_at_iso=now.isoformat(),
        ), lease

    def _active_lease(self, lease_id: str, nonce: str, now: datetime) -> TaskLease:
        lease = self.leases[lease_id]
        if lease.nonce != nonce or lease.status != "active":
            raise ValueError("lease is not active or nonce does not match")
        if _parse_iso(lease.expires_at_iso) <= now:
            self.expire(at=now)
            raise ValueError("lease has expired")
        return lease

    def renew(self, lease_id: str, nonce: str, *, at: datetime | None = None) -> TaskLease:
        now = _aware(at or datetime.now(timezone.utc))
        lease = self._active_lease(lease_id, nonce, now)
        agent = self.agents[lease.agent_id]
        renewed = lease.model_copy(update={
            "heartbeat_at_iso": now.isoformat(),
            "expires_at_iso": (now + timedelta(seconds=agent.lease_ttl_seconds)).isoformat(),
        })
        self.leases[lease_id] = renewed
        return renewed

    def complete(self, lease_id: str, nonce: str, *, success: bool, at: datetime | None = None) -> ExecutionTask:
        now = _aware(at or datetime.now(timezone.utc))
        lease = self._active_lease(lease_id, nonce, now)
        self.leases[lease_id] = lease.model_copy(update={"status": "released", "heartbeat_at_iso": now.isoformat()})
        task = self.tasks[lease.task_id]
        task = task.model_copy(update={"status": "completed" if success else "failed", "updated_at_iso": now.isoformat()})
        self.tasks[task.task_id] = task
        return task

    def expire(self, *, at: datetime | None = None) -> list[str]:
        now = _aware(at or datetime.now(timezone.utc))
        expired: list[str] = []
        for lease_id, lease in list(self.leases.items()):
            if lease.status != "active":
                continue
            if _parse_iso(lease.expires_at_iso) <= now:
                self.leases[lease_id] = lease.model_copy(update={"status": "expired"})
                task = self.tasks[lease.task_id]
                next_status = "queued" if task.attempt < task.max_attempts else "expired"
                self.tasks[task.task_id] = task.model_copy(update={
                    "status": next_status,
                    "attempt": min(task.max_attempts, task.attempt + 1),
                    "assigned_agent_id": None,
                    "updated_at_iso": now.isoformat(),
                })
                expired.append(lease_id)
        return expired
