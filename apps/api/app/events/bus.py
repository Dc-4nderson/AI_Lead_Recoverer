"""Event bus (§16).

Two responsibilities kept separate on purpose:
  1. durability + audit  — every event is written to event_log
  2. fan-out             — dispatch to in-process subscribers, isolated so one
                           subscriber's failure can't block others

MVP transport is in-process synchronous dispatch. The public interface
(publish / subscribe) is stable, so swapping the dispatcher for Redis pub/sub
or a broker later touches only this module — no publisher or subscriber
changes, mirroring the QueueClient pattern (§9).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import TypeVar

from app.core.db import session_scope
from app.events.types import BaseEvent
from app.models import EventLog

logger = logging.getLogger("events.bus")

EventT = TypeVar("EventT", bound=BaseEvent)
Handler = Callable[[BaseEvent], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type[BaseEvent], handler: Handler) -> None:
        self._subscribers[event_type.event_type].append(handler)

    async def publish(self, event: BaseEvent) -> None:
        # 1. Durability / audit / replay.
        await self._persist(event)
        # Observability: record the event when a simulation is active (no-op in prod).
        from app.simulator.session import get_current_simulation

        sim = get_current_simulation()
        handlers = self._subscribers.get(event.event_type, [])
        event_rec = None
        if sim is not None:
            event_rec = sim.trace.record_event(event.event_type, event.to_payload())
            event_rec["subscriber_count"] = len(handlers)
        # 2. Fan-out with per-subscriber isolation.
        for handler in handlers:
            started = perf_counter()
            try:
                await handler(event)
                if sim is not None:
                    sim.trace.record_subscriber(
                        event.event_type, getattr(handler, "__name__", repr(handler)),
                        "ok", (perf_counter() - started) * 1000, None,
                    )
            except Exception as exc:  # noqa: BLE001 — one bad subscriber must not block others
                logger.exception(
                    "event subscriber failed", extra={"event_type": event.event_type}
                )
                if sim is not None:
                    sim.trace.record_subscriber(
                        event.event_type, getattr(handler, "__name__", repr(handler)),
                        "error", (perf_counter() - started) * 1000, repr(exc),
                    )

    async def _persist(self, event: BaseEvent) -> None:
        org_id = getattr(event, "organization_id", None)
        async with session_scope() as session:
            session.add(
                EventLog(
                    organization_id=org_id,
                    event_type=event.event_type,
                    payload=event.to_payload(),
                    occurred_at=event.occurred_at,
                )
            )


# Process-wide singleton. Handlers are registered once at startup (app.main
# lifespan → app.events.handlers.register_all_handlers).
event_bus = EventBus()
