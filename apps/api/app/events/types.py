"""Typed, versioned domain events (§16).

Each event declares an ``event_type`` string with an embedded version
(e.g. ``lead.qualified.v1``) so schema evolution never breaks historical
event_log rows or slow subscribers.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    event_type: ClassVar[str]
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_payload(self) -> dict:
        return self.model_dump(mode="json")


class MissedCallDetected(BaseEvent):
    event_type: ClassVar[str] = "missed_call.detected.v1"
    organization_id: uuid.UUID
    phone_number_id: uuid.UUID
    caller_number: str
    call_sid: str


class SMSSent(BaseEvent):
    event_type: ClassVar[str] = "sms.sent.v1"
    organization_id: uuid.UUID
    conversation_id: uuid.UUID
    message_sid: str | None = None


class MessageReceived(BaseEvent):
    event_type: ClassVar[str] = "message.received.v1"
    organization_id: uuid.UUID
    conversation_id: uuid.UUID
    body: str
    provider_message_sid: str


class LeadQualified(BaseEvent):
    event_type: ClassVar[str] = "lead.qualified.v1"
    organization_id: uuid.UUID
    lead_id: uuid.UUID
    classification: Literal["new_lead", "existing_customer", "emergency", "spam"]


class AppointmentRequested(BaseEvent):
    event_type: ClassVar[str] = "appointment.requested.v1"
    organization_id: uuid.UUID
    lead_id: uuid.UUID
    preferred_time: datetime | None = None
