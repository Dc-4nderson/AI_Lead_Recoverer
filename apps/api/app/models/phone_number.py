from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.shared.enums import ConnectionType, ForwardingStatus, PhoneStatus


class PhoneNumber(UUIDMixin, TimestampMixin, Base):
    """Dual-path phone number (§17a).

    ``e164_number`` is always the number Twilio physically receives calls/SMS
    on — tenant resolution keys off this regardless of connection_type.
    ``business_number`` holds the customer's real published line for the
    forwarding path.
    """

    __tablename__ = "phone_numbers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    connection_type: Mapped[ConnectionType] = mapped_column(String(24), nullable=False)
    e164_number: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    business_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    twilio_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    forwarding_status: Mapped[ForwardingStatus | None] = mapped_column(String(24), nullable=True)
    status: Mapped[PhoneStatus] = mapped_column(
        String(20), default=PhoneStatus.PROVISIONING, nullable=False
    )
