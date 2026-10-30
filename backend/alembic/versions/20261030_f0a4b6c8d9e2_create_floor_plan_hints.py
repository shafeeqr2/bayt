"""create floor plan hints (room completion by the text model)

Revision ID: f0a4b6c8d9e2
Revises: e9f3a5b7c8d1
Create Date: 2026-10-30 06:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f0a4b6c8d9e2'
down_revision: str | Sequence[str] | None = 'e9f3a5b7c8d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'floor_plan_hints',
        sa.Column('listing_id', sa.String(length=32), nullable=False),
        sa.Column('model', sa.Text(), nullable=False),
        sa.Column('prompt_version', sa.Integer(), nullable=False),
        sa.Column('hints', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('listing_id'),
    )


def downgrade() -> None:
    op.drop_table('floor_plan_hints')
