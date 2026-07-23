from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any, ClassVar, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from .base import SchemaModel


class MaintenanceWindow(SchemaModel):
    kind: ClassVar[str] = "MaintenanceWindow"

    window_id: str
    organization_id: str
    workspace_id: str
    name: str
    timezone: str = "UTC"
    days_of_week: set[int] = Field(default_factory=lambda: set(range(7)))
    start_local_time: str = "00:00"
    duration_minutes: int = Field(default=60, ge=1, le=10080)
    allowed_operation_types: set[str] = Field(default_factory=set)
    target_ids: set[str] = Field(default_factory=set)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone {value!r}") from exc
        return value

    @field_validator("days_of_week")
    @classmethod
    def valid_days(cls, value: set[int]) -> set[int]:
        if not value or any(day < 0 or day > 6 for day in value):
            raise ValueError("days_of_week must contain values from 0 (Monday) through 6 (Sunday)")
        return value

    @field_validator("start_local_time")
    @classmethod
    def valid_time(cls, value: str) -> str:
        try:
            time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("start_local_time must be HH:MM or HH:MM:SS") from exc
        return value


class ScheduledOperation(SchemaModel):
    kind: ClassVar[str] = "ScheduledOperation"

    schedule_id: str
    organization_id: str
    workspace_id: str
    target_type: Literal["environment", "fleet"]
    target_id: str
    operation_type: str
    lifecycle_profile_id: str | None = None
    policy_id: str | None = None
    execution_mode: Literal["dry_run", "simulation", "guarded_execution"] = "dry_run"
    not_before_iso: str | None = None
    deadline_iso: str | None = None
    maintenance_window_id: str | None = None
    materialize_automatically: bool = False
    status: Literal[
        "pending", "delayed", "ready", "materialized", "blocked", "expired", "cancelled"
    ] = "pending"
    operation_id: str | None = None
    fleet_plan_id: str | None = None
    created_by: str
    created_at_iso: str
    updated_at_iso: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_schedule(self) -> "ScheduledOperation":
        if self.target_type == "environment" and not self.lifecycle_profile_id:
            raise ValueError("environment schedules require lifecycle_profile_id")
        if self.status == "materialized" and not (self.operation_id or self.fleet_plan_id):
            raise ValueError("materialized schedules require operation_id or fleet_plan_id")
        parsed: dict[str, datetime] = {}
        for field_name in ("created_at_iso", "updated_at_iso", "not_before_iso", "deadline_iso"):
            value = getattr(self, field_name)
            if value is None:
                continue
            try:
                instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"{field_name} must be ISO-8601") from exc
            parsed[field_name] = instant if instant.tzinfo else instant.replace(tzinfo=timezone.utc)
        if parsed.get("deadline_iso") and parsed.get("not_before_iso") and parsed["deadline_iso"] < parsed["not_before_iso"]:
            raise ValueError("deadline_iso must not precede not_before_iso")
        if parsed.get("updated_at_iso") and parsed.get("created_at_iso") and parsed["updated_at_iso"] < parsed["created_at_iso"]:
            raise ValueError("updated_at_iso must not precede created_at_iso")
        return self


class ScheduleDecision(SchemaModel):
    kind: ClassVar[str] = "ScheduleDecision"

    decision_id: str
    schedule_id: str
    outcome: Literal["ready", "delay", "deny", "expired", "terminal"]
    reasons: list[str] = Field(default_factory=list)
    evaluated_at_iso: str
    next_eligible_at_iso: str | None = None
    window_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
