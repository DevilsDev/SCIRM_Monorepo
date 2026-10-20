"""Embeddings on public signals for vector search (Evidence Engine v2).

Each vector is stored with the model that produced it and a hash of the text it
embeds (title and summary). Retrieval only compares vectors from the configured
model, and a record whose text changes (shortage summaries do) is re-embedded.

The dimension (1536) is Cohere Embed v4's default; another model means a new
migration.

Revision ID: 014
Revises: 013
Create Date: 2026-10-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE public_signals ADD COLUMN embedding vector(1536)")
    op.execute("ALTER TABLE public_signals ADD COLUMN embedding_model text")
    op.execute("ALTER TABLE public_signals ADD COLUMN embedding_text_hash text")
    op.execute("CREATE INDEX ix_public_signals_embedding ON public_signals USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_public_signals_embedding")
    for col in ("embedding_text_hash", "embedding_model", "embedding"):
        op.execute(f"ALTER TABLE public_signals DROP COLUMN IF EXISTS {col}")
