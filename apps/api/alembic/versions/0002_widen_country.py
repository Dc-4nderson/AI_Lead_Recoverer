"""widen business_settings.country from VARCHAR(2) to VARCHAR(100)

Revision ID: 0002_widen_country
Revises: 0001_initial
Create Date: 2026-07-22

The original column only fit an ISO code; onboarding sends free-text country
names (e.g. "United States"), which overflowed VARCHAR(2) and 500'd on save.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_widen_country"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "business_settings",
        "country",
        existing_type=sa.String(2),
        type_=sa.String(100),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "business_settings",
        "country",
        existing_type=sa.String(100),
        type_=sa.String(2),
        existing_nullable=True,
    )
