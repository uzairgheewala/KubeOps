from __future__ import annotations

import signal
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from api.models import ScheduledOperationRecord
from api.scheduling import evaluate_schedule_record, materialize_schedule_record


class Command(BaseCommand):
    help = (
        "Evaluate durable scheduled operations and optionally materialize ready requests. "
        "Materialization only creates a normal governed operation or fleet plan; it never "
        "approves, dispatches, or executes it."
    )

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-seconds", type=float, default=30.0)
        parser.add_argument("--workspace-id", default=None)
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        if options["poll_seconds"] <= 0:
            raise CommandError("--poll-seconds must be positive")
        if options["limit"] < 1:
            raise CommandError("--limit must be at least 1")
        self.stop_requested = False
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stop_requested", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "stop_requested", True))

        while not self.stop_requested:
            processed = self._run_once(options["workspace_id"], options["limit"])
            if options["once"]:
                break
            if processed == 0:
                time.sleep(options["poll_seconds"])

    def _run_once(self, workspace_id: str | None, limit: int) -> int:
        queryset = ScheduledOperationRecord.objects.filter(
            status__in=["pending", "delayed", "ready", "blocked"]
        ).select_related("organization", "workspace", "maintenance_window", "fleet", "operation")
        if workspace_id:
            queryset = queryset.filter(workspace__workspace_id=workspace_id)

        processed = 0
        for schedule_id in list(queryset.order_by("not_before", "created_at").values_list("schedule_id", flat=True)[:limit]):
            try:
                with transaction.atomic():
                    record = (
                        ScheduledOperationRecord.objects.select_for_update(skip_locked=True)
                        .select_related("organization", "workspace", "maintenance_window", "fleet", "operation")
                        .get(schedule_id=schedule_id)
                    )
                    schedule, decision = evaluate_schedule_record(record, at=timezone.now())
                    if decision.outcome == "ready" and schedule.materialize_automatically:
                        schedule, decision, _ = materialize_schedule_record(record)
                    processed += 1
                    self.stdout.write(
                        f"{schedule.schedule_id}: {decision.outcome} -> {schedule.status}"
                    )
            except ScheduledOperationRecord.DoesNotExist:
                continue
            except Exception as exc:  # Scheduler must isolate one bad request from the queue.
                ScheduledOperationRecord.objects.filter(schedule_id=schedule_id).update(
                    status="blocked",
                    updated_at=timezone.now(),
                )
                record = ScheduledOperationRecord.objects.filter(schedule_id=schedule_id).first()
                if record:
                    payload = dict(record.payload)
                    metadata = dict(payload.get("metadata", {}))
                    metadata["scheduler_error"] = f"{type(exc).__name__}: {exc}"
                    payload["metadata"] = metadata
                    payload["status"] = "blocked"
                    payload["updated_at_iso"] = timezone.now().isoformat()
                    record.payload = payload
                    record.save(update_fields=["payload"])
                self.stderr.write(self.style.ERROR(f"{schedule_id}: {type(exc).__name__}: {exc}"))
        return processed
