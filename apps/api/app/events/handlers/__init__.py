"""Event-bus subscriber registration (§16).

Subscribers are deliberately thin: translate a domain event into an enqueued
job. Keeping the event-handling path fast + retryable is why work happens in
the queue, not inline in the handler.

register_all_handlers() is idempotent-ish (it clears then re-registers) and is
called once at API startup and once at worker startup.
"""
from __future__ import annotations

import logging

from app.events.bus import event_bus
from app.events.types import LeadQualified, MessageReceived, MissedCallDetected

logger = logging.getLogger("events.handlers")


async def _get_queue():
    # Lazy import breaks the handlers → arq_backend → tasks → handlers cycle.
    from app.queue.arq_backend import get_queue_client

    return await get_queue_client()


async def _on_missed_call(event: MissedCallDetected) -> None:
    queue = await _get_queue()
    await queue.enqueue(
        "handle_missed_call",
        str(event.organization_id),
        str(event.phone_number_id),
        event.caller_number,
        event.call_sid,
    )


async def _on_message_received(event: MessageReceived) -> None:
    queue = await _get_queue()
    await queue.enqueue(
        "process_inbound_sms",
        str(event.organization_id),
        str(event.conversation_id),
        event.body,
        event.provider_message_sid,
    )


async def _on_lead_qualified(event: LeadQualified) -> None:
    queue = await _get_queue()
    await queue.enqueue(
        "send_notification",
        str(event.organization_id),
        str(event.lead_id),
        "sms",
        event.classification == "emergency",
    )


def register_all_handlers() -> None:
    event_bus._subscribers.clear()  # noqa: SLF001 — intentional idempotent reset
    event_bus.subscribe(MissedCallDetected, _on_missed_call)  # type: ignore[arg-type]
    event_bus.subscribe(MessageReceived, _on_message_received)  # type: ignore[arg-type]
    event_bus.subscribe(LeadQualified, _on_lead_qualified)  # type: ignore[arg-type]
    logger.info("event handlers registered")


__all__ = ["register_all_handlers"]
