"""create listing profiles, persona profiles and similar results (pgvector)

Revision ID: e9f3a5b7c8d1
Revises: d8e2f4a1b6c3
Create Date: 2026-10-28 02:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = 'e9f3a5b7c8d1'
down_revision: str | Sequence[str] | None = 'd8e2f4a1b6c3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 2048


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.create_table(
        'listing_profiles',
        sa.Column('listing_id', sa.String(length=32), nullable=False),
        sa.Column('model', sa.Text(), nullable=False),
        sa.Column('prompt_version', sa.Integer(), nullable=False),
        sa.Column('facts', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('listing_id'),
    )
    op.create_table(
        'listing_persona_profiles',
        sa.Column('listing_id', sa.String(length=32), nullable=False),
        sa.Column('persona', sa.String(length=32), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('pitch', sa.Text(), nullable=False),
        sa.Column('signals', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('concerns', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('embedding', Vector(EMBEDDING_DIM), nullable=True),
        sa.Column('embed_model', sa.Text(), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('listing_id', 'persona'),
    )
    op.create_index('ix_listing_persona_profiles_score', 'listing_persona_profiles', ['score'])
    op.create_table(
        'similar_results',
        sa.Column('listing_id', sa.String(length=32), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('model', sa.Text(), nullable=False),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('listing_id', 'request_hash'),
    )


def downgrade() -> None:
    op.drop_table('similar_results')
    op.drop_index('ix_listing_persona_profiles_score', table_name='listing_persona_profiles')
    op.drop_table('listing_persona_profiles')
    op.drop_table('listing_profiles')
