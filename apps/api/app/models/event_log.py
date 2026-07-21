from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import UUIDMixin


class EventLog(UUIDMixin, Base):
    """Durable record of every published event (§16).

    Provides audit/observability and lets new subscribers replay history
    rather than only seeing events from when they started listening.
    """

    __tablename__ = "event_log"
    __table_args__ = (
        Index("ix_event_log_org_type_time", "organization_id", "event_type", "occurred_at"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)  # e.g. lead.qualified.v1
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
