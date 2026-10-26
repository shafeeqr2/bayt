"""create listing_photos

Revision ID: d8e2f4a1b6c3
Revises: c7a1f2d9e4b5
Create Date: 2026-10-25 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd8e2f4a1b6c3'
down_revision: str | Sequence[str] | None = 'c7a1f2d9e4b5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'listing_photos',
        sa.Column('listing_id', sa.String(length=32), nullable=False),
        sa.Column('photo_index', sa.Integer(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('model', sa.Text(), nullable=False),
        sa.Column('prompt_version', sa.Integer(), nullable=False),
        sa.Column('facts', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('listing_id', 'photo_index'),
    )


def downgrade() -> None:
    op.drop_table('listing_photos')
