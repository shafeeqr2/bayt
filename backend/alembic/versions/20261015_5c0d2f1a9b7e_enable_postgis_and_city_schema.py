"""enable postgis and city schema

Revision ID: 5c0d2f1a9b7e
Revises: 1be4a2cf4738
Create Date: 2026-10-15 03:30:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = '5c0d2f1a9b7e'
down_revision: str | Sequence[str] | None = '1be4a2cf4738'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    # City of Toronto open data, loaded by `./start.sh city-data`.
    op.execute("CREATE SCHEMA IF NOT EXISTS city")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS city CASCADE")
    op.execute("DROP EXTENSION IF EXISTS postgis")
