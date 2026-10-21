"""Per-tenant ERP connections (SAP S/4HANA over OData).

One connection per organization and system. The password is stored encrypted
(libs/common/secret_box.py: AES-256-GCM, bound to "erp:<system>:<org>:<id>"), never in
plaintext, and is never returned by the API. Tenant-scoped with forced row-level
security, like the other tenant tables.

Revision ID: 018
Revises: 017
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE erp_connections (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            system text NOT NULL CHECK (system IN ('sap')),
            base_url text NOT NULL CHECK (length(base_url) <= 500),
            sap_client text NULL CHECK (sap_client ~ '^[0-9]{3}$'),
            username text NOT NULL CHECK (length(username) <= 200),
            password_enc text NOT NULL CHECK (password_enc LIKE 'enc:v1:%'),
            last_test jsonb NULL,
            last_import jsonb NULL,
            created_by text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT erp_connections_one_per_system UNIQUE (organization_id, system)
        )
    """)
    op.execute("ALTER TABLE erp_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE erp_connections FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY erp_connections_org_isolation ON erp_connections
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org())
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS erp_connections")
