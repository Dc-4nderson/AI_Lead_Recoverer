"""TraceCollector — captures everything that happens during one simulation.

Records are plain dicts so the whole trace serializes straight to JSON for the
API/frontend. Every record carries a monotonic ``seq`` (ordering) and an ISO
timestamp. Categories: event, subscriber, workflow_step, queue_job, ai_call,
db_change, sms, timeline.
"""
from __future__ import annotations

import itertools
from datetime import UTC, datetime
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


class TraceCollector:
    def __init__(self) -> None:
        self._seq = itertools.count(1)
        self.events: list[dict[str, Any]] = []
        self.subscribers: list[dict[str, Any]] = []
        self.workflow_steps: list[dict[str, Any]] = []
        self.queue_jobs: list[dict[str, Any]] = []
        self.ai_calls: list[dict[str, Any]] = []
        self.db_changes: list[dict[str, Any]] = []
        self.sms: list[dict[str, Any]] = []
        self.timeline: list[dict[str, Any]] = []

    def _rec(self, **fields: Any) -> dict[str, Any]:
        return {"seq": next(self._seq), "ts": _now(), **fields}

    # --- Event bus ---
    def record_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        rec = self._rec(event_type=event_type, payload=payload, subscriber_count=0)
        self.events.append(rec)
        self.add_timeline(event_type, kind="event")
        return rec

    def record_subscriber(
        self, event_type: str, handler: str, status: str, duration_ms: float, error: str | None
    ) -> None:
        self.subscribers.append(
            self._rec(
                event_type=event_type,
                handler=handler,
                status=status,
                duration_ms=round(duration_ms, 2),
                error=error,
            )
        )

    # --- Workflow engine ---
    def record_workflow_step(
        self, workflow: str, step: str, outcome: str, workflow_run_id: str, state: dict[str, Any]
    ) -> None:
        self.workflow_steps.append(
            self._rec(
                workflow=workflow,
                step=step,
                outcome=outcome,
                workflow_run_id=workflow_run_id,
                state=state,
            )
        )
        self.add_timeline(f"{step} → {outcome}", kind="workflow_step")

    # --- Queue ---
    def record_queue_job(self, task_name: str) -> dict[str, Any]:
        rec = self._rec(
            task_name=task_name,
            status="queued",
            retries=0,
            duration_ms=None,
            error=None,
        )
        self.queue_jobs.append(rec)
        return rec

    # --- AI extraction ---
    def record_ai_call(self, **fields: Any) -> None:
        self.ai_calls.append(self._rec(**fields))
        self.add_timeline("AI Extraction", kind="ai_call")

    # --- DB changes ---
    def record_db_change(
        self, table: str, operation: str, pk: str, before: dict | None, after: dict | None
    ) -> None:
        self.db_changes.append(
            self._rec(table=table, operation=operation, pk=pk, before=before, after=after)
        )

    # --- Outbound SMS / notifications ---
    def record_sms(self, to_number: str, from_number: str, body: str, kind: str) -> None:
        self.sms.append(
            self._rec(to_number=to_number, from_number=from_number, body=body, sms_kind=kind)
        )
        self.add_timeline(f"{kind}: {body[:40]}", kind="sms")

    # --- Timeline ---
    def add_timeline(self, label: str, kind: str) -> None:
        self.timeline.append(self._rec(label=label, timeline_kind=kind))

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": self.events,
            "subscribers": self.subscribers,
            "workflow_steps": self.workflow_steps,
            "queue_jobs": self.queue_jobs,
            "ai_calls": self.ai_calls,
            "db_changes": self.db_changes,
            "sms": self.sms,
            "timeline": sorted(self.timeline, key=lambda r: r["seq"]),
        }
