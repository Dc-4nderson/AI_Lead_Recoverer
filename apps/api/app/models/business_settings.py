from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin


class BusinessSettings(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "business_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Accepts a full country name or an ISO code — kept forgiving so onboarding
    # never fails on a reasonable free-text address entry.
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # {mon: [{"open": "09:00", "close": "17:00"}], ...}
    business_hours: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # ["drain cleaning", "install", ...]
    services_offered: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    emergency_service_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    ai_tone: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_custom_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    # {"sms": true, "email": [...], "owner_phone": "+1..."}
    notification_preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
