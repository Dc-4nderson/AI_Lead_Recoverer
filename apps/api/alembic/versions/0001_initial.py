"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-21

Creates the full MVP schema (§3). Kept as an explicit hand-written migration
so `alembic upgrade head` works on a fresh database; subsequent changes should
use `alembic revision --autogenerate`.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
TS = sa.DateTime(timezone=True)


def _uuid_pk() -> sa.Column:
    return sa.Column("id", UUID, primary_key=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "organizations",
        _uuid_pk(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(120)),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("status", sa.String(20), nullable=False, server_default="trial"),
        *_timestamps(),
    )

    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_email_verified", sa.Boolean, nullable=False, server_default=sa.false()),
        *_timestamps(),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "memberships",
        _uuid_pk(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False, server_default="owner"),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "organization_id"),
    )
    op.create_index("ix_memberships_organization_id", "memberships", ["organization_id"])

    op.create_table(
        "business_settings",
        _uuid_pk(),
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("address_line1", sa.String(255)),
        sa.Column("city", sa.String(120)),
        sa.Column("state", sa.String(120)),
        sa.Column("postal_code", sa.String(20)),
        sa.Column("country", sa.String(2)),
        sa.Column("business_hours", JSONB, nullable=False, server_default="{}"),
        sa.Column("services_offered", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "emergency_service_enabled", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("ai_tone", sa.Text),
        sa.Column("ai_custom_instructions", sa.Text),
        sa.Column("notification_preferences", JSONB, nullable=False, server_default="{}"),
        *_timestamps(),
    )

    op.create_table(
        "phone_numbers",
        _uuid_pk(),
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("connection_type", sa.String(24), nullable=False),
        sa.Column("e164_number", sa.String(20), nullable=False, unique=True),
        sa.Column("business_number", sa.String(20)),
        sa.Column("twilio_sid", sa.String(64)),
        sa.Column("forwarding_status", sa.String(24)),
        sa.Column("status", sa.String(20), nullable=False, server_default="provisioning"),
        *_timestamps(),
    )
    op.create_index("ix_phone_numbers_organization_id", "phone_numbers", ["organization_id"])
    op.create_index("ix_phone_numbers_e164_number", "phone_numbers", ["e164_number"])

    op.create_table(
        "leads",
        _uuid_pk(),
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("service_requested", sa.Text),
        sa.Column("location", sa.Text),
        sa.Column("urgency", sa.String(20)),
        sa.Column("preferred_time", TS),
        sa.Column("classification", sa.String(24)),
        sa.Column("status", sa.String(28), nullable=False, server_default="new"),
        *_timestamps(),
    )
    op.create_index("ix_leads_org_phone", "leads", ["organization_id", "phone_number"])

    op.create_table(
        "conversations",
        _uuid_pk(),
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lead_id", UUID, sa.ForeignKey("leads.id", ondelete="SET NULL")),
        sa.Column("twilio_sid", sa.String(64)),
        sa.Column("call_sid", sa.String(64)),
        sa.Column("channel", sa.String(12), nullable=False, server_default="sms"),
        sa.Column("started_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("last_message_at", TS),
    )
    op.create_index("ix_conversations_organization_id", "conversations", ["organization_id"])
    op.create_index("ix_conversations_call_sid", "conversations", ["call_sid"])

    op.create_table(
        "messages",
        _uuid_pk(),
        sa.Column(
            "conversation_id",
            UUID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction", sa.String(12), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("provider_message_sid", sa.String(64), unique=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "event_log",
        _uuid_pk(),
        sa.Column(
            "organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE")
        ),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("occurred_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_event_log_org_type_time",
        "event_log",
        ["organization_id", "event_type", "occurred_at"],
    )

    op.create_table(
        "workflow_runs",
        _uuid_pk(),
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workflow_name", sa.String(120), nullable=False),
        sa.Column("trigger_event_id", UUID, sa.ForeignKey("event_log.id", ondelete="SET NULL")),
        sa.Column(
            "conversation_id", UUID, sa.ForeignKey("conversations.id", ondelete="SET NULL")
        ),
        sa.Column("lead_id", UUID, sa.ForeignKey("leads.id", ondelete="SET NULL")),
        sa.Column("state", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        *_timestamps(),
    )
    op.create_index("ix_workflow_runs_organization_id", "workflow_runs", ["organization_id"])

    op.create_table(
        "audit_logs",
        _uuid_pk(),
        sa.Column(
            "organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE")
        ),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(120), nullable=False),
        sa.Column("entity_id", sa.String(64)),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    for table in [
        "audit_logs",
        "workflow_runs",
        "event_log",
        "messages",
        "conversations",
        "leads",
        "phone_numbers",
        "business_settings",
        "memberships",
        "users",
        "organizations",
    ]:
        op.drop_table(table)
