"""create lot_analyses

Revision ID: 7c2e9a41d5b3
Revises: 03c5c2685707
Create Date: 2026-10-15 00:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '7c2e9a41d5b3'
down_revision: str | Sequence[str] | None = '03c5c2685707'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'lot_analyses',
        sa.Column('listing_id', sa.String(length=32), nullable=False),
        sa.Column('parcel_id', sa.Integer(), nullable=True),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('listing_id'),
    )
    op.create_index(op.f('ix_lot_analyses_parcel_id'), 'lot_analyses', ['parcel_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_lot_analyses_parcel_id'), table_name='lot_analyses')
    op.drop_table('lot_analyses')
