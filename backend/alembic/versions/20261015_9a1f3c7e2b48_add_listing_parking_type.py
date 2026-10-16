"""add listing parking type

Revision ID: 9a1f3c7e2b48
Revises: 7c2e9a41d5b3
Create Date: 2026-10-15 20:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9a1f3c7e2b48'
down_revision: str | Sequence[str] | None = '7c2e9a41d5b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('listings', sa.Column('parking_type', sa.Text(), nullable=True))
    # Backfill from the stored source payload so existing databases need no re-seed.
    op.execute(
        "UPDATE listings SET parking_type = NULLIF(raw->'Property'->>'ParkingType', '')"
    )


def downgrade() -> None:
    op.drop_column('listings', 'parking_type')
