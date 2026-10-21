"""create listing_investment

Revision ID: 4e8b2d7f1a9c
Revises: 9a1f3c7e2b48
Create Date: 2026-10-16 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '4e8b2d7f1a9c'
down_revision: str | Sequence[str] | None = '9a1f3c7e2b48'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'listing_investment',
        sa.Column('listing_id', sa.String(length=32), nullable=False),
        sa.Column('model_version', sa.Integer(), nullable=False),
        sa.Column('rent_monthly', sa.Integer(), nullable=False),
        sa.Column('rent_source', sa.Text(), nullable=False),
        sa.Column('rent_note', sa.Text(), nullable=False),
        sa.Column('units', sa.Integer(), nullable=False),
        sa.Column('gross_annual', sa.Integer(), nullable=False),
        sa.Column('expenses_annual', sa.Integer(), nullable=False),
        sa.Column('noi_annual', sa.Integer(), nullable=False),
        sa.Column('gross_yield_pct', sa.Float(), nullable=False),
        sa.Column('cap_rate_pct', sa.Float(), nullable=False),
        sa.Column('has_suite', sa.Boolean(), nullable=False),
        sa.Column('suite_potential', sa.Boolean(), nullable=False),
        sa.Column('suite_note', sa.Text(), nullable=True),
        sa.Column('extra_bedroom_room', sa.Text(), nullable=True),
        sa.Column('garden_suite', sa.Text(), nullable=True),
        sa.Column('severance', sa.Text(), nullable=True),
        sa.Column('as_of_right_units', sa.Integer(), nullable=True),
        sa.Column('multiplex_zone', sa.Boolean(), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('listing_id'),
    )
    op.create_index(op.f('ix_listing_investment_cap_rate_pct'), 'listing_investment', ['cap_rate_pct'], unique=False)
    op.create_index(op.f('ix_listing_investment_noi_annual'), 'listing_investment', ['noi_annual'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_listing_investment_noi_annual'), table_name='listing_investment')
    op.drop_index(op.f('ix_listing_investment_cap_rate_pct'), table_name='listing_investment')
    op.drop_table('listing_investment')
