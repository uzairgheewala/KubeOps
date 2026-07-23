from __future__ import annotations

from datetime import datetime, timedelta, timezone, time
import hashlib
import json
from zoneinfo import ZoneInfo

from kubeops_core.models.scheduling import MaintenanceWindow, ScheduledOperation, ScheduleDecision


_TERMINAL = {"materialized", "expired", "cancelled"}


def _parse(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class SchedulingService:
    """Evaluate durable operation schedules without bypassing operation policy."""

    def evaluate(
        self,
        schedule: ScheduledOperation,
        windows: list[MaintenanceWindow],
        *,
        at: datetime | None = None,
    ) -> ScheduleDecision:
        now = at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if schedule.status in _TERMINAL:
            return self._decision(schedule, "terminal", now, [f"schedule is {schedule.status}"])
        deadline = _parse(schedule.deadline_iso)
        if deadline is not None and now > deadline:
            return self._decision(schedule, "expired", now, ["schedule deadline has passed"])
        not_before = _parse(schedule.not_before_iso)
        if not_before is not None and now < not_before:
            return self._decision(
                schedule, "delay", now, ["schedule is before not_before"], next_at=not_before
            )
        if schedule.maintenance_window_id is None:
            return self._decision(schedule, "ready", now, ["no maintenance window required"])
        window = next(
            (item for item in windows if item.window_id == schedule.maintenance_window_id), None
        )
        if window is None:
            return self._decision(schedule, "deny", now, ["maintenance window is unavailable"])
        if not window.enabled:
            return self._decision(schedule, "deny", now, ["maintenance window is disabled"], window=window)
        if window.organization_id != schedule.organization_id or window.workspace_id != schedule.workspace_id:
            return self._decision(schedule, "deny", now, ["maintenance window scope mismatch"], window=window)
        if window.allowed_operation_types and schedule.operation_type not in window.allowed_operation_types:
            return self._decision(schedule, "deny", now, ["operation type is not permitted by maintenance window"], window=window)
        if window.target_ids and schedule.target_id not in window.target_ids:
            return self._decision(schedule, "deny", now, ["target is not permitted by maintenance window"], window=window)
        inside, next_open = self._window_state(window, now)
        if inside:
            return self._decision(schedule, "ready", now, ["maintenance window is open"], window=window)
        if deadline is not None and next_open is not None and next_open > deadline:
            return self._decision(schedule, "expired", now, ["no maintenance window opens before deadline"], window=window)
        return self._decision(
            schedule, "delay", now, ["waiting for maintenance window"], next_at=next_open, window=window
        )

    @staticmethod
    def _window_state(window: MaintenanceWindow, now: datetime) -> tuple[bool, datetime | None]:
        zone = ZoneInfo(window.timezone)
        local_now = now.astimezone(zone)
        parsed_time = time.fromisoformat(window.start_local_time)
        candidates: list[tuple[datetime, datetime]] = []
        # Include yesterday because windows may cross midnight, then search the next week.
        for offset in range(-1, 9):
            day = local_now.date() + timedelta(days=offset)
            if day.weekday() not in window.days_of_week:
                continue
            start_local = datetime.combine(day, parsed_time, tzinfo=zone)
            end_local = start_local + timedelta(minutes=window.duration_minutes)
            candidates.append((start_local, end_local))
        for start, end in candidates:
            if start <= local_now < end:
                return True, start.astimezone(timezone.utc)
        future = [start for start, _ in candidates if start > local_now]
        return False, min(future).astimezone(timezone.utc) if future else None

    @staticmethod
    def _decision(
        schedule: ScheduledOperation,
        outcome: str,
        now: datetime,
        reasons: list[str],
        *,
        next_at: datetime | None = None,
        window: MaintenanceWindow | None = None,
    ) -> ScheduleDecision:
        evaluated_at = now.astimezone(timezone.utc).isoformat()
        next_eligible = next_at.astimezone(timezone.utc).isoformat() if next_at else None
        window_id = window.window_id if window else schedule.maintenance_window_id
        identity = json.dumps(
            {
                "schedule_id": schedule.schedule_id, "outcome": outcome, "reasons": reasons,
                "evaluated_at_iso": evaluated_at, "next_eligible_at_iso": next_eligible,
                "window_id": window_id,
            },
            sort_keys=True, separators=(",", ":"),
        )
        decision_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return ScheduleDecision(
            decision_id=f"schedule-decision:{decision_hash}",
            schedule_id=schedule.schedule_id,
            outcome=outcome,
            reasons=reasons,
            evaluated_at_iso=evaluated_at,
            next_eligible_at_iso=next_eligible,
            window_id=window_id,
            metadata={"operation_type": schedule.operation_type, "target_type": schedule.target_type},
        )
