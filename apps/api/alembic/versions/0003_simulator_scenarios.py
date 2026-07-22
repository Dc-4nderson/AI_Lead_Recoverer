"""simulator_scenarios table

Revision ID: 0003_simulator_scenarios
Revises: 0002_widen_country
Create Date: 2026-07-22

Stores reusable Workflow Simulator inputs (developer tooling). The payload is
the exact simulator run request so saved scenarios can seed regression tests.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_simulator_scenarios"
down_revision = "0002_widen_country"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "simulator_scenarios",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_simulator_scenarios_organization_id", "simulator_scenarios", ["organization_id"]
    )


def downgrade() -> None:
    op.drop_table("simulator_scenarios")
