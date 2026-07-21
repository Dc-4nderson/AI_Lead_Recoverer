from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.shared.enums import Classification, LeadStatus, Urgency


class Lead(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (Index("ix_leads_org_phone", "organization_id", "phone_number"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)  # caller's number

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    service_requested: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency: Mapped[Urgency | None] = mapped_column(String(20), nullable=True)
    preferred_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    classification: Mapped[Classification | None] = mapped_column(String(24), nullable=True)
    status: Mapped[LeadStatus] = mapped_column(
        String(28), default=LeadStatus.NEW, nullable=False
    )
