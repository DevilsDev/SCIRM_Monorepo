"""Add Row-Level Security policies for multi-tenancy and MFA columns.

Revision ID: 003
Revises: 002
Create Date: 2026-04-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- MFA columns on users ---
    op.add_column("users", sa.Column("mfa_secret", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("mfa_enabled", sa.Boolean, server_default="false"))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime, nullable=True))

    # --- Row-Level Security ---
    # The application sets the tenant per transaction:
    #   SET LOCAL app.current_org_id = '<org uuid>'
    # Policies fail closed: with no tenant set, no rows are visible or writable.
    # FORCE applies the policies to the table owner too. Superusers and roles with
    # BYPASSRLS still skip RLS, so the app must connect as an ordinary role.
    op.execute(f"""
        CREATE OR REPLACE FUNCTION {CURRENT_ORG_FN}() RETURNS uuid
        LANGUAGE sql STABLE AS $$
            SELECT NULLIF(current_setting('app.current_org_id', true), '')::uuid
        $$
    """)

    for table in DIRECT_ORG_TABLES:
        _enable_rls(table, f"organization_id = {CURRENT_ORG_FN}()")

    # Child tables are scoped through their parent row; the parent's own policy
    # filters the subquery, so a child is visible only if its parent is.
    for table, predicate in CHILD_TABLE_POLICIES.items():
        _enable_rls(table, predicate)


CURRENT_ORG_FN = "scirm_current_org"

DIRECT_ORG_TABLES = ["suppliers", "risk_assessments", "alerts", "agent_runs", "rag_collections"]

CHILD_TABLE_POLICIES = {
    "risks": "EXISTS (SELECT 1 FROM risk_assessments a WHERE a.id = assessment_id)",
    "recommendations": "EXISTS (SELECT 1 FROM risk_assessments a WHERE a.id = assessment_id)",
    "quality_reviews": "EXISTS (SELECT 1 FROM risk_assessments a WHERE a.id = assessment_id)",
    "quality_issues": "EXISTS (SELECT 1 FROM quality_reviews r WHERE r.id = review_id)",
    "agent_steps": "EXISTS (SELECT 1 FROM agent_runs r WHERE r.id = run_id)",
    "rag_documents": "EXISTS (SELECT 1 FROM rag_collections c WHERE c.id = collection_id)",
    "rag_chunks": "EXISTS (SELECT 1 FROM rag_documents d WHERE d.id = document_id)",
}


def _enable_rls(table: str, predicate: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {table}_org_isolation ON {table}
        USING ({predicate})
        WITH CHECK ({predicate})
    """)


def _disable_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {table}_org_isolation ON {table}")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(list(CHILD_TABLE_POLICIES)):
        _disable_rls(table)
    for table in reversed(DIRECT_ORG_TABLES):
        _disable_rls(table)
    op.execute(f"DROP FUNCTION IF EXISTS {CURRENT_ORG_FN}()")

    op.drop_column("users", "last_login_at")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_secret")
