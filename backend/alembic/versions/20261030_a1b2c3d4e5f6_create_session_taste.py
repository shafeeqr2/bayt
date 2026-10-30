"""create session events and session taste (phase 4 of similar homes)

Revision ID: a1b2c3d4e5f6
Revises: f0a4b6c8d9e2
Create Date: 2026-10-30 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: str | Sequence[str] | None = 'f0a4b6c8d9e2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'session_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('listing_id', sa.String(length=32), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('via', sa.String(length=16), nullable=True),
        sa.Column('persona', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_session_events_session_id', 'session_events', ['session_id'])
    op.create_table(
        'session_taste',
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('actions', sa.Integer(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('persona', sa.String(length=32), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('likes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('model', sa.Text(), nullable=False),
        sa.Column('prompt_version', sa.Integer(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('session_id'),
    )


def downgrade() -> None:
    op.drop_table('session_taste')
    op.drop_index('ix_session_events_session_id', table_name='session_events')
    op.drop_table('session_events')
