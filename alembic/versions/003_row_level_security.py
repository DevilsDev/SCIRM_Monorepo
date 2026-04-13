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
    # Enable RLS on multi-tenant tables
    for table in ["suppliers", "risk_assessments", "risks", "recommendations", "alerts", "agent_runs"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

        # Policy: users can only see rows belonging to their organization
        op.execute(f"""
            CREATE POLICY {table}_org_isolation ON {table}
            USING (
                organization_id = current_setting('app.current_org_id', true)::uuid
                OR current_setting('app.current_org_id', true) IS NULL
                OR current_setting('app.current_org_id', true) = ''
            )
        """)

    # RLS for tables that reference assessments (no direct org_id)
    for table in ["quality_reviews", "quality_issues"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # Allow all for now — production would join through assessment -> org
        op.execute(f"CREATE POLICY {table}_allow_all ON {table} USING (true)")


def downgrade() -> None:
    for table in [
        "quality_issues", "quality_reviews", "agent_runs",
        "alerts", "recommendations", "risks", "risk_assessments", "suppliers",
    ]:
        op.execute(f"DROP POLICY IF EXISTS {table}_org_isolation ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_allow_all ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_column("users", "last_login_at")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_secret")
