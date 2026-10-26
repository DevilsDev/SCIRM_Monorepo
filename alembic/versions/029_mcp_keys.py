"""API keys may have the scope 'mcp': a connection for an MCP client (an AI agent such as
Claude), which can call only the MCP server at /mcp. Still exactly one scope per key.

Revision ID: 029
Revises: 028
Create Date: 2026-10-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE api_keys DROP CONSTRAINT api_keys_scopes_check")
    op.execute("ALTER TABLE api_keys ADD CONSTRAINT api_keys_scopes_check "
               "CHECK (scopes <@ ARRAY['read', 'scim', 'mcp']::text[] AND cardinality(scopes) = 1)")


def downgrade() -> None:
    op.execute("DELETE FROM api_keys WHERE 'mcp' = ANY(scopes)")
    op.execute("ALTER TABLE api_keys DROP CONSTRAINT api_keys_scopes_check")
    op.execute("ALTER TABLE api_keys ADD CONSTRAINT api_keys_scopes_check "
               "CHECK (scopes <@ ARRAY['read', 'scim']::text[] AND cardinality(scopes) = 1)")
