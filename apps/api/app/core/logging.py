"""Structured JSON logging (§12).

One log line per request/job, carrying org_id / request_id / workflow_run_id
where available via a contextvar, so tracing a lead end-to-end is one query.
"""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

# Request/job-scoped correlation fields, threaded through service and worker calls.
# Default is None (never a shared mutable dict); readers coalesce to {}.
log_context: ContextVar[dict[str, str] | None] = ContextVar("log_context", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(log_context.get() or {})
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def bind_log_context(**fields: str) -> None:
    """Merge correlation fields into the current context."""
    current = dict(log_context.get() or {})
    current.update({k: v for k, v in fields.items() if v is not None})
    log_context.set(current)
