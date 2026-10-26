"""Align the schema with what the services persist, and make the audit log
tenant-scoped and append-only.

Revision ID: 009
Revises: 008
Create Date: 2026-10-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB_EMPTY = sa.text("'{}'::jsonb")


def upgrade() -> None:
    # --- Assessments keep a snapshot of the full response for /tasks/{id}/result.
    op.add_column("risk_assessments", sa.Column("result", postgresql.JSONB, nullable=True))

    # --- Risks: manual risks have no assessment, so scope them to the org directly.
    op.alter_column("risks", "assessment_id", nullable=True)
    op.add_column("risks", sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                                     sa.ForeignKey("organizations.id"), nullable=True))
    # Backfill existing rows from their assessment, then require it.
    op.execute("""
        UPDATE risks r SET organization_id = a.organization_id
        FROM risk_assessments a WHERE a.id = r.assessment_id AND r.organization_id IS NULL
    """)
    op.execute("DELETE FROM risks WHERE organization_id IS NULL")
    op.alter_column("risks", "organization_id", nullable=False)
    op.add_column("risks", sa.Column("status", sa.String(20), server_default="open", nullable=False))
    op.add_column("risks", sa.Column("owner", sa.String(255), nullable=True))
    op.add_column("risks", sa.Column("details", postgresql.JSONB, server_default=JSONB_EMPTY, nullable=False))
    op.add_column("risks", sa.Column("updated_at", sa.DateTime, server_default=sa.text("now()")))
    op.create_index("ix_risks_org_severity", "risks", ["organization_id", "severity"])
    op.execute("DROP POLICY risks_org_isolation ON risks")
    op.execute("""
        CREATE POLICY risks_org_isolation ON risks
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org())
    """)

    op.add_column("recommendations", sa.Column("details", postgresql.JSONB, server_default=JSONB_EMPTY, nullable=False))

    # --- Events: the UI's event types are not a fixed set; store as text, validate in the app.
    op.execute("ALTER TABLE risk_events ALTER COLUMN event_type TYPE varchar(50) USING event_type::text")
    op.execute("DROP TYPE IF EXISTS event_type_enum")
    op.add_column("event_impacts", sa.Column("details", postgresql.JSONB, server_default=JSONB_EMPTY, nullable=False))

    # --- Audit log: tenant-scoped, actor recorded, append-only.
    op.add_column("audit_logs", sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("audit_logs", sa.Column("actor_type", sa.String(20), server_default="user", nullable=False))
    op.add_column("audit_logs", sa.Column("actor", sa.String(255), nullable=True))
    op.add_column("audit_logs", sa.Column("status_code", sa.Integer, nullable=True))
    op.create_index("ix_audit_org_created", "audit_logs", ["organization_id", "created_at"])
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY")
    # Tenants see their own rows. Rows with no organization (e.g. a failed login for
    # an unknown email) can be written but are visible to no tenant.
    op.execute("""
        CREATE POLICY audit_logs_org_isolation ON audit_logs
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org() OR organization_id IS NULL)
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION scirm_audit_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only';
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER audit_logs_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION scirm_audit_append_only()
    """)
    op.execute("""
        CREATE TRIGGER audit_logs_no_truncate
        BEFORE TRUNCATE ON audit_logs
        FOR EACH STATEMENT EXECUTE FUNCTION scirm_audit_append_only()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_truncate ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update_delete ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS scirm_audit_append_only()")
    op.execute("DROP POLICY IF EXISTS audit_logs_org_isolation ON audit_logs")
    op.execute("ALTER TABLE audit_logs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_audit_org_created", table_name="audit_logs")
    for col in ("status_code", "actor", "actor_type", "organization_id"):
        op.drop_column("audit_logs", col)

    op.drop_column("event_impacts", "details")
    op.execute("""
        CREATE TYPE event_type_enum AS ENUM ('natural_disaster', 'geopolitical', 'regulatory_change',
            'cyber_attack', 'financial_distress', 'quality_failure', 'logistics_disruption')
    """)
    op.execute("ALTER TABLE risk_events ALTER COLUMN event_type TYPE event_type_enum USING event_type::event_type_enum")

    op.drop_column("recommendations", "details")

    op.execute("DROP POLICY risks_org_isolation ON risks")
    op.execute("""
        CREATE POLICY risks_org_isolation ON risks
        USING (EXISTS (SELECT 1 FROM risk_assessments a WHERE a.id = assessment_id))
        WITH CHECK (EXISTS (SELECT 1 FROM risk_assessments a WHERE a.id = assessment_id))
    """)
    op.drop_index("ix_risks_org_severity", table_name="risks")
    # Manually entered risks have no assessment and cannot exist in the old schema.
    op.execute("DELETE FROM risks WHERE assessment_id IS NULL")
    for col in ("updated_at", "details", "owner", "status", "organization_id"):
        op.drop_column("risks", col)
    op.alter_column("risks", "assessment_id", nullable=False)

    op.drop_column("risk_assessments", "result")
