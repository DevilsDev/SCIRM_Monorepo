"""Human rights and environmental due diligence (LkSG, CSDDD) on suppliers.

- dd_settings: the organization's review interval for a supplier's risk analysis (LkSG
  section 5(4): once a year; CSDDD Article 15: at least every five years).
- dd_risks: a supplier's risk register. Each risk is in one area of the law (LkSG section 2,
  CSDDD Annex), rated by a person (likelihood and severity, 1-4, with a reason) and says
  where it came from (scoping, in-depth assessment, the supplier's questionnaire, an
  incident, a public record or a notification received).
- dd_measures: prevention, correction and remediation measures, including the last-resort
  steps, with an owner, a due date, a status and a review of their effectiveness.
- dd_events: everything that happens to the register, including each review of a
  supplier's risk analysis. Append-only for the application, like the audit log.

The documentation has to be kept for seven years (LkSG section 10(1)), so none of these
rows can be deleted by the application (DELETE and TRUNCATE are revoked in
scripts/db_setup.py) and they reference suppliers without a cascade: a supplier with due
diligence records cannot be deleted, only deactivated.

supplier_assessments.request_reason: why the information was asked for. Under CSDDD
Article 8(2a) a company asks a business partner for information only where it is needed.

Revision ID: 032
Revises: 031
Create Date: 2026-10-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OWN_SUPPLIER = "EXISTS (SELECT 1 FROM suppliers s WHERE s.id = supplier_id)"
AREAS = ("child_labour", "worst_forms_child_labour", "forced_labour", "slavery", "occupational_safety",
         "freedom_of_association", "discrimination", "fair_wage", "environmental_harm_to_people", "land_rights",
         "security_forces", "workers_housing", "other_human_rights", "mercury_products", "mercury_processes",
         "mercury_waste", "persistent_organic_pollutants", "pops_waste", "hazardous_waste_export",
         "hazardous_waste_annex_vii", "hazardous_waste_import", "hazardous_chemicals_trade", "biodiversity",
         "marine_pollution")
SOURCES = ("scoping", "in_depth", "supplier_reported", "incident", "public_record", "notification")
KINDS = ("code_of_conduct", "training", "audit", "corrective_action_plan", "industry_initiative",
         "purchasing_practice", "remediation", "enhanced_prevention_plan", "refrain_new_business", "suspend",
         "terminate", "other")


def _in(values) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _isolate(table: str, extra: str = "") -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    check = f"organization_id = scirm_current_org(){' AND ' + extra if extra else ''}"
    op.execute(f"CREATE POLICY {table}_org_isolation ON {table} "
               f"USING (organization_id = scirm_current_org()) WITH CHECK ({check})")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE dd_settings (
            organization_id uuid PRIMARY KEY REFERENCES organizations(id),
            review_months smallint NOT NULL DEFAULT 12 CHECK (review_months BETWEEN 1 AND 60),
            updated_by text NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    _isolate("dd_settings")

    op.execute(f"""
        CREATE TABLE dd_risks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            supplier_id uuid NOT NULL REFERENCES suppliers(id),
            area text NOT NULL CHECK (area IN {_in(AREAS)}),
            description text NOT NULL CHECK (length(description) BETWEEN 1 AND 2000),
            likelihood smallint NOT NULL CHECK (likelihood BETWEEN 1 AND 4),
            severity smallint NOT NULL CHECK (severity BETWEEN 1 AND 4),
            rating_reason text NOT NULL CHECK (length(rating_reason) BETWEEN 1 AND 2000),
            source text NOT NULL CHECK (source IN {_in(SOURCES)}),
            source_ref text NULL CHECK (length(source_ref) <= 200),
            status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'mitigated', 'closed')),
            assessed_by text NULL,
            assessed_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_dd_risks_supplier ON dd_risks (organization_id, supplier_id)")
    _isolate("dd_risks", OWN_SUPPLIER)

    op.execute(f"""
        CREATE TABLE dd_measures (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            supplier_id uuid NOT NULL REFERENCES suppliers(id),
            risk_id uuid NULL REFERENCES dd_risks(id),
            kind text NOT NULL CHECK (kind IN {_in(KINDS)}),
            description text NOT NULL CHECK (length(description) BETWEEN 1 AND 2000),
            owner_email text NULL CHECK (length(owner_email) <= 254),
            due_date date NULL,
            status text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'in_progress', 'done', 'cancelled')),
            effectiveness text NOT NULL DEFAULT 'not_reviewed'
                CHECK (effectiveness IN ('not_reviewed', 'effective', 'partly_effective', 'not_effective')),
            effectiveness_note text NULL CHECK (length(effectiveness_note) <= 2000),
            created_by text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_dd_measures_supplier ON dd_measures (organization_id, supplier_id)")
    _isolate("dd_measures", f"{OWN_SUPPLIER} AND (risk_id IS NULL OR EXISTS "
                            f"(SELECT 1 FROM dd_risks r WHERE r.id = risk_id AND r.supplier_id = dd_measures.supplier_id))")

    op.execute("""
        CREATE TABLE dd_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            seq bigint GENERATED ALWAYS AS IDENTITY,
            organization_id uuid NOT NULL REFERENCES organizations(id),
            supplier_id uuid NOT NULL REFERENCES suppliers(id),
            risk_id uuid NULL REFERENCES dd_risks(id),
            measure_id uuid NULL REFERENCES dd_measures(id),
            kind text NOT NULL CHECK (kind IN ('risk_added', 'risk_rated', 'risk_status', 'measure_added',
                                               'measure_status', 'measure_reviewed', 'analysis_reviewed')),
            text text NOT NULL CHECK (length(text) BETWEEN 1 AND 4000),
            actor text NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_dd_events_supplier ON dd_events (organization_id, supplier_id, seq)")
    op.execute("CREATE INDEX ix_dd_events_kind ON dd_events (organization_id, kind, created_at)")
    _isolate("dd_events", OWN_SUPPLIER)

    op.execute("ALTER TABLE supplier_assessments ADD COLUMN request_reason text NULL "
               "CHECK (length(request_reason) <= 1000)")


def downgrade() -> None:
    op.execute("ALTER TABLE supplier_assessments DROP COLUMN IF EXISTS request_reason")
    for table in ("dd_events", "dd_measures", "dd_risks", "dd_settings"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
