"""init schema

Revision ID: 0001
Revises:
Create Date: 2026-01-07
"""

from __future__ import annotations

from alembic import op


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from models.database import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    from models.database import Base

    Base.metadata.drop_all(bind=op.get_bind())
