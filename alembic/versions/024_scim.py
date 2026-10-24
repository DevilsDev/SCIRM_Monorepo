"""SCIM 2.0 user provisioning.

- api_keys may now have the scope 'scim' (exactly one scope per key): a SCIM token, which
  can call only /scim/v2 and nothing else; read keys cannot call /scim/v2.
- users.scim_external_id: the identity provider's own id for the user (externalId).

Revision ID: 024
Revises: 023
Create Date: 2026-10-23
"""
from typing import Sequence, Union

from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE api_keys DROP CONSTRAINT api_keys_scopes_check")
    op.execute("ALTER TABLE api_keys ADD CONSTRAINT api_keys_scopes_check "
               "CHECK (scopes <@ ARRAY['read', 'scim']::text[] AND cardinality(scopes) = 1)")
    op.execute("ALTER TABLE users ADD COLUMN scim_external_id text NULL CHECK (length(scim_external_id) <= 200)")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS scim_external_id")
    op.execute("DELETE FROM api_keys WHERE 'scim' = ANY(scopes)")
    op.execute("ALTER TABLE api_keys DROP CONSTRAINT api_keys_scopes_check")
    op.execute("ALTER TABLE api_keys ADD CONSTRAINT api_keys_scopes_check CHECK (scopes <@ ARRAY['read']::text[])")
