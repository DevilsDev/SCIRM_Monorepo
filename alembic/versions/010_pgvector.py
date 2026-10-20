"""Enable pgvector for the Evidence Engine (embeddings stored in the main database,
so they inherit the same tenant row-level security).

Revision ID: 010
Revises: 009
Create Date: 2026-10-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
