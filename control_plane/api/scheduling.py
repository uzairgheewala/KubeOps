from __future__ import annotations

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from kubeops_core.fleet import FleetService
from kubeops_core.models import (
    FleetDefinition,
    MaintenanceWindow,
    OperationalProfileAssessment,
    ScheduledOperation,
    ScheduleDecision,
)
from kubeops_core.scheduling import SchedulingService

from .governance import evaluate_governance, mark_governance_usage_terminal
from .models import (
    EnvironmentRecord,
    FleetRecord,
    MaintenanceWindowRecord,
    OperationRecord,
    ScheduledOperationRecord,
)
from .services import lifecycle_planner_for_workspace, lifecycle_registry_for_workspace, operation_runtime_for_workspace


def _dt(value: str | None):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def evaluate_schedule_record(
    record: ScheduledOperationRecord, *, at: datetime | None = None
) -> tuple[ScheduledOperation, ScheduleDecision]:
    schedule = ScheduledOperation.model_validate(record.payload)
    windows = [
        MaintenanceWindow.model_validate(item.payload)
        for item in MaintenanceWindowRecord.objects.filter(workspace=record.workspace)
    ]
    decision = SchedulingService().evaluate(schedule, windows, at=at)
    next_status = {
        "ready": "ready",
        "delay": "delayed",
        "deny": "blocked",
        "expired": "expired",
        "terminal": schedule.status,
    }[decision.outcome]
    updated = schedule.model_copy(
        update={
            "status": next_status,
            "updated_at_iso": timezone.now().isoformat(),
            "metadata": {**schedule.metadata, "last_schedule_decision": decision.model_dump(mode="json")},
        }
    )
    record.status = updated.status
    record.payload = updated.model_dump(mode="json")
    record.updated_at = _dt(updated.updated_at_iso)
    record.save(update_fields=["status", "payload", "updated_at"])
    return updated, decision


def materialize_schedule_record(record: ScheduledOperationRecord):  # type: ignore[no-untyped-def]
    """Create a normal guarded operation or fleet plan without bypassing approval policy."""

    schedule, decision = evaluate_schedule_record(record)
    if decision.outcome != "ready":
        return schedule, decision, None
    if schedule.target_type == "fleet":
        fleet_record = FleetRecord.objects.get(
            fleet_id=schedule.target_id, workspace=record.workspace
        )
        plan = FleetService().plan_operation(
            FleetDefinition.model_validate(fleet_record.payload), schedule.operation_type
        )
        updated = schedule.model_copy(
            update={
                "status": "materialized",
                "fleet_plan_id": plan.plan_id,
                "updated_at_iso": timezone.now().isoformat(),
                "metadata": {**schedule.metadata, "fleet_plan": plan.model_dump(mode="json")},
            }
        )
        record.fleet = fleet_record
        record.status = updated.status
        record.payload = updated.model_dump(mode="json")
        record.updated_at = _dt(updated.updated_at_iso)
        record.save(update_fields=["fleet", "status", "payload", "updated_at"])
        return updated, decision, plan

    environment = EnvironmentRecord.objects.get(
        environment_id=schedule.target_id, workspace=record.workspace, active=True
    )
    snapshot_record = environment.snapshots.first()
    if snapshot_record is None:
        blocked = schedule.model_copy(
            update={
                "status": "blocked",
                "updated_at_iso": timezone.now().isoformat(),
                "metadata": {**schedule.metadata, "materialization_blocker": "environment has no snapshot"},
            }
        )
        record.status = blocked.status
        record.payload = blocked.model_dump(mode="json")
        record.updated_at = _dt(blocked.updated_at_iso)
        record.save(update_fields=["status", "payload", "updated_at"])
        return blocked, decision, None

    active_count = OperationRecord.objects.filter(
        environment__workspace=record.workspace
    ).exclude(status__in=["completed", "failed", "cancelled"]).count()
    governance = evaluate_governance(
        workspace=record.workspace,
        operation="operation.create",
        active_count=active_count,
        target_id=environment.environment_id,
    )
    if governance.outcome != "allow":
        delayed = schedule.model_copy(
            update={
                "status": "delayed",
                "updated_at_iso": timezone.now().isoformat(),
                "metadata": {**schedule.metadata, "materialization_governance": governance.model_dump(mode="json")},
            }
        )
        record.status = delayed.status
        record.payload = delayed.model_dump(mode="json")
        record.updated_at = _dt(delayed.updated_at_iso)
        record.save(update_fields=["status", "payload", "updated_at"])
        return delayed, decision, governance

    try:
        from .views import _persist_operation, _snapshot

        workspace_id = record.workspace.workspace_id
        profile = lifecycle_registry_for_workspace(workspace_id).get(schedule.lifecycle_profile_id or "")
        snapshot = _snapshot(snapshot_record)
        assessment_record = snapshot_record.assessments.filter(
            profile_id=profile.target_operational_profile_id
        ).first()
        assessment = (
            OperationalProfileAssessment.model_validate(assessment_record.payload)
            if assessment_record else None
        )
        plan = lifecycle_planner_for_workspace(workspace_id).plan(
            profile,
            snapshot,
            assessment,
            mode=schedule.execution_mode,
            policy_id=schedule.policy_id,
        )
        operation = operation_runtime_for_workspace(workspace_id).create(
            environment.environment_id, plan, mode=schedule.execution_mode
        )
        operation = operation.model_copy(
            update={"metadata": {**operation.metadata, "scheduled_operation_id": schedule.schedule_id}}
        )
        operation_record, _ = _persist_operation(operation, environment, snapshot_record=snapshot_record)
        updated = schedule.model_copy(
            update={
                "status": "materialized",
                "operation_id": operation.operation_id,
                "updated_at_iso": timezone.now().isoformat(),
                "metadata": {
                    **schedule.metadata,
                    "materialization_governance": governance.model_dump(mode="json"),
                },
            }
        )
        with transaction.atomic():
            record.operation = operation_record
            record.status = updated.status
            record.payload = updated.model_dump(mode="json")
            record.updated_at = _dt(updated.updated_at_iso)
            record.save(update_fields=["operation", "status", "payload", "updated_at"])
        return updated, decision, operation
    finally:
        mark_governance_usage_terminal(
            workspace=record.workspace,
            operation="operation.create",
            target_id=environment.environment_id,
        )
