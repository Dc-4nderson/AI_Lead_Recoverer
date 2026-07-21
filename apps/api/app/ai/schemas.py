"""Structured output contract for the AI extraction layer (§17b).

The AI layer's entire job is to turn conversation text into ONE of these,
schema-validated. It never decides side effects — the workflow engine does.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.shared.enums import Classification, Urgency


class LeadExtractionResult(BaseModel):
    name: str | None = Field(default=None, description="Caller's name if stated")
    service_requested: str | None = Field(
        default=None, description="Service the caller is asking about"
    )
    location: str | None = Field(default=None, description="Service location / address")
    urgency: Urgency | None = Field(default=None, description="How urgent the request is")
    preferred_time: str | None = Field(
        default=None, description="Preferred appointment time, as stated (free text)"
    )
    classification: Classification | None = Field(
        default=None, description="Lead classification"
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Which qualification fields are still unknown and worth asking about",
    )
    suggested_reply: str | None = Field(
        default=None,
        description="A natural next SMS to send, honoring tone. Advisory only — "
        "the workflow decides whether/what to send.",
    )
