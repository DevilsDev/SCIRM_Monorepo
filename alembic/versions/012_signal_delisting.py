"""Mark public signals that their source no longer lists.

FDA publishes shortages and import-alert Red Lists as current lists: a resolved
shortage or a firm removed from the Red List simply disappears. Keeping such
rows active would keep telling customers that a supplier is in shortage or
detained at the border after FDA cleared it. They are marked delisted instead
of deleted, which also builds the dated listing history FDA does not publish.

Revision ID: 012
Revises: 011
Create Date: 2026-10-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("public_signals", sa.Column("delisted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_public_signals_active_source", "public_signals", ["source"],
                    postgresql_where=sa.text("delisted_at IS NULL"))


def downgrade() -> None:
    op.drop_index("ix_public_signals_active_source", table_name="public_signals")
    op.drop_column("public_signals", "delisted_at")
