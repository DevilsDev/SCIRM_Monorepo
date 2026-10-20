"""Keyword search over public signals for the Evidence Engine (libs/evidence).

A generated tsvector on the signal itself, rather than a copied chunks table, so
search can never return a record that matching would not: delisted rows are
filtered the same way. Titles weigh more than summaries; company names are in
the summary for every company-specific source.

Vector search comes later, once an embedding provider is chosen (the column's
dimension depends on the model).

Revision ID: 013
Revises: 012
Create Date: 2026-10-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE public_signals ADD COLUMN search_doc tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english'::regconfig, coalesce(summary, '')), 'B')
        ) STORED
    """)
    op.execute("CREATE INDEX ix_public_signals_search ON public_signals USING gin (search_doc)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_public_signals_search")
    op.execute("ALTER TABLE public_signals DROP COLUMN IF EXISTS search_doc")
