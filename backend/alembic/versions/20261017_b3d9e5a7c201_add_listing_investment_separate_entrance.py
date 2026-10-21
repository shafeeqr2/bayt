"""add listing_investment.separate_entrance

Revision ID: b3d9e5a7c201
Revises: 4e8b2d7f1a9c
Create Date: 2026-10-17 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b3d9e5a7c201'
down_revision: str | Sequence[str] | None = '4e8b2d7f1a9c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('listing_investment', sa.Column('separate_entrance', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('listing_investment', 'separate_entrance')
