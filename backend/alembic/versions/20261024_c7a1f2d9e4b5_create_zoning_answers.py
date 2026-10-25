"""create zoning_answers

Revision ID: c7a1f2d9e4b5
Revises: b3d9e5a7c201
Create Date: 2026-10-24 20:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c7a1f2d9e4b5'
down_revision: str | Sequence[str] | None = 'b3d9e5a7c201'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'zoning_answers',
        sa.Column('listing_id', sa.String(length=32), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('model', sa.Text(), nullable=False),
        sa.Column('prompt_version', sa.Integer(), nullable=False),
        sa.Column('intent', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('answer', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('listing_id', 'request_hash'),
    )


def downgrade() -> None:
    op.drop_table('zoning_answers')
