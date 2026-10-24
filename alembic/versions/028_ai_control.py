"""AI control centre: a log of AI runs, the action policy and the approval queue.

- ai_runs: one row per AI run (Ask, and later MCP tool calls): who asked what, which model
  answered (or that none did), the method, what the citation checker kept and removed,
  whether the run was degraded, and how long it took. Append-only for the application
  (UPDATE and DELETE are revoked in scripts/db_setup.py), like the audit log.
- action_policies: per organization and action, what an AI agent may do: never, propose it
  for a person's approval, or do it directly. Actions that reach outside the organization
  (emailing a supplier) can be at most "approval" (enforced by the application).
- action_proposals: actions proposed by an agent, waiting for a person; approved ones run
  through the same code and permission checks as when a person does them.

All three are tenant tables with forced row-level security. The old agent_runs and
agent_steps tables (migration 002) were never written to and are left unused.

Revision ID: 028
Revises: 027
Create Date: 2026-10-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _isolate(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_org_isolation ON {table} USING (organization_id = scirm_current_org()) "
               f"WITH CHECK (organization_id = scirm_current_org())")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE ai_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            seq bigint GENERATED ALWAYS AS IDENTITY,
            organization_id uuid NOT NULL REFERENCES organizations(id),
            kind text NOT NULL CHECK (kind IN ('ask', 'mcp_tool')),
            actor text NULL CHECK (length(actor) <= 254),
            actor_type text NOT NULL DEFAULT 'user' CHECK (actor_type IN ('user', 'api_key')),
            status text NOT NULL CHECK (length(status) BETWEEN 1 AND 40),
            method text NULL CHECK (length(method) <= 60),
            degraded boolean NOT NULL DEFAULT false,
            input jsonb NOT NULL DEFAULT '{}',
            output jsonb NOT NULL DEFAULT '{}',
            llm jsonb NULL,
            latency_ms integer NULL CHECK (latency_ms >= 0),
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_ai_runs_org_seq ON ai_runs (organization_id, seq DESC)")
    _isolate("ai_runs")

    op.execute("""
        CREATE TABLE action_policies (
            organization_id uuid NOT NULL REFERENCES organizations(id),
            action text NOT NULL CHECK (length(action) BETWEEN 1 AND 60),
            mode text NOT NULL CHECK (mode IN ('never', 'approval', 'allowed')),
            updated_by text NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (organization_id, action)
        )
    """)
    _isolate("action_policies")

    op.execute("""
        CREATE TABLE action_proposals (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            action text NOT NULL CHECK (length(action) BETWEEN 1 AND 60),
            params jsonb NOT NULL DEFAULT '{}',
            summary text NOT NULL CHECK (length(summary) BETWEEN 1 AND 500),
            proposed_by text NOT NULL CHECK (length(proposed_by) <= 254),
            proposed_via text NOT NULL CHECK (proposed_via IN ('mcp', 'agent')),
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'executed', 'rejected', 'failed')),
            decided_by text NULL,
            decided_at timestamptz NULL,
            decision_note text NULL CHECK (length(decision_note) <= 1000),
            result jsonb NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_action_proposals_status ON action_proposals (organization_id, status, created_at DESC)")
    _isolate("action_proposals")


def downgrade() -> None:
    for table in ("action_proposals", "action_policies", "ai_runs"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
