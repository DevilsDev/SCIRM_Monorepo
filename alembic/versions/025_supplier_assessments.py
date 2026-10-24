"""Supplier assessments and the supplier portal.

- assessment_templates: an organization's own questionnaires (the built-in ones live in
  code, libs/assessments/questions.py). Tenant table with forced row-level security.
- supplier_assessments: a questionnaire sent to one supplier contact. The questions are
  copied in when it is sent, so editing a template never changes what a supplier saw. The
  supplier answers through the portal with a link; only the SHA-256 of the link's token is
  stored, it expires, and it stops working once the answers are submitted, the assessment
  is cancelled or the link is re-sent (a new token). Scores are computed by code.
- supplier_subtier_links: the supplier's own suppliers, as the supplier reported them in
  an assessment. Kept apart from public-record matches: these are claims, not findings.

The portal works before anyone signs in, so scirm_assessment_by_token (SECURITY DEFINER,
like the login lookup) turns a live token into its assessment and organization; every
other step then runs as the application role inside that organization. The two tables it
reads are therefore enabled, not forced, for row-level security (like password_resets):
the application role still sees only its own organization's rows.

The policies also require the supplier to be visible in the current organization, so an
assessment or link can never point at another organization's supplier.

Revision ID: 025
Revises: 024
Create Date: 2026-10-24
"""
from typing import Sequence, Union

from alembic import op

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OWN_SUPPLIER = "EXISTS (SELECT 1 FROM suppliers s WHERE s.id = supplier_id)"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE assessment_templates (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
            description text NOT NULL DEFAULT '' CHECK (length(description) <= 500),
            questions jsonb NOT NULL CHECK (jsonb_typeof(questions) = 'array'),
            archived boolean NOT NULL DEFAULT false,
            created_by text NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("ALTER TABLE assessment_templates ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE assessment_templates FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY assessment_templates_org_isolation ON assessment_templates
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org())
    """)

    op.execute("""
        CREATE TABLE supplier_assessments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            supplier_id uuid NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
            template_name text NOT NULL CHECK (length(template_name) BETWEEN 1 AND 100),
            questions jsonb NOT NULL CHECK (jsonb_typeof(questions) = 'array'),
            status text NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'submitted', 'reviewed', 'cancelled')),
            recipient_email text NOT NULL CHECK (length(recipient_email) BETWEEN 3 AND 254),
            recipient_name text NOT NULL DEFAULT '' CHECK (length(recipient_name) <= 200),
            due_date date NULL,
            token_hash text NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
            token_expires_at timestamptz NULL,
            answers jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(answers) = 'object'),
            submitted_by_name text NULL,
            submitted_by_email text NULL,
            submitted_at timestamptz NULL,
            score smallint NULL CHECK (score BETWEEN 0 AND 100),
            flags jsonb NOT NULL DEFAULT '[]',
            review_note text NULL CHECK (length(review_note) <= 2000),
            reviewed_by text NULL,
            reviewed_at timestamptz NULL,
            sent_by text NULL,
            sent_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT supplier_assessments_live_token CHECK (status = 'sent' OR token_hash IS NULL)
        )
    """)
    op.execute("CREATE INDEX ix_supplier_assessments_supplier ON supplier_assessments (organization_id, supplier_id)")
    op.execute("ALTER TABLE supplier_assessments ENABLE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY supplier_assessments_org_isolation ON supplier_assessments
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org() AND {OWN_SUPPLIER})
    """)

    op.execute("""
        CREATE TABLE supplier_subtier_links (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            supplier_id uuid NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
            assessment_id uuid NOT NULL REFERENCES supplier_assessments(id) ON DELETE CASCADE,
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
            country_code varchar(2) NULL,
            city text NULL CHECK (length(city) <= 100),
            supplies text NULL CHECK (length(supplies) <= 200),
            reported_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_supplier_subtier_links_supplier ON supplier_subtier_links (organization_id, supplier_id)")
    op.execute("ALTER TABLE supplier_subtier_links ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE supplier_subtier_links FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY supplier_subtier_links_org_isolation ON supplier_subtier_links
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org() AND {OWN_SUPPLIER})
    """)

    op.execute("""
        CREATE FUNCTION scirm_assessment_by_token(p_token_hash text)
        RETURNS TABLE (id uuid, organization_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
            SELECT a.id, a.organization_id FROM supplier_assessments a
            WHERE a.token_hash = p_token_hash AND a.status = 'sent' AND a.token_expires_at > now()
        $$
    """)
    op.execute("REVOKE ALL ON FUNCTION scirm_assessment_by_token(text) FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS scirm_assessment_by_token(text)")
    op.execute("DROP TABLE IF EXISTS supplier_subtier_links")
    op.execute("DROP TABLE IF EXISTS supplier_assessments")
    op.execute("DROP TABLE IF EXISTS assessment_templates")
