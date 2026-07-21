"""Execution context passed to every workflow step (§17).

The engine and its steps depend only on this context's injected collaborators
(SMS sender, AI extraction, notifier, event publisher) — never on concrete
integration clients directly. That's what makes the engine unit-testable with
zero OpenAI/Twilio calls: tests pass a context with fakes.
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.ai.schemas import LeadExtractionResult
from app.events.types import BaseEvent


class SMSSender(Protocol):
    async def send(self, *, to_number: str, from_number: str, body: str) -> str | None: ...


class Extractor(Protocol):
    async def extract(self, *, conversation_id: uuid.UUID) -> LeadExtractionResult: ...


class Notifier(Protocol):
    async def notify_owner(
        self, *, organization_id: uuid.UUID, lead_id: uuid.UUID, urgent: bool
    ) -> None: ...


@dataclass
class WorkflowContext:
    organization_id: uuid.UUID
    workflow_run_id: uuid.UUID
    conversation_id: uuid.UUID
    lead_id: uuid.UUID | None
    caller_number: str
    business_number: str  # our Twilio-side number, the SMS "from"
    state: dict[str, Any]

    # Injected collaborators (deterministic engine depends only on these).
    sms: SMSSender
    extractor: Extractor
    notifier: Notifier
    publish_event: Callable[[BaseEvent], Awaitable[None]]

    # Populated by steps during a run.
    last_extraction: LeadExtractionResult | None = field(default=None)
