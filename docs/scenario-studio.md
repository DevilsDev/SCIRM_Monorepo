# Scenario studio and resilience planner

**Intelligence → Scenario studio** answers "what if these suppliers were out for N weeks?"
with numbers computed by code from your own data, and lists what would reduce the damage
most. Nothing is estimated by AI. Everyone can run scenarios; administrators and analysts
save them.

## What it measures

**Purchase spend at risk**, not revenue: SCIRM knows each supplier's 12-month purchase spend
from the [SAP spend import](sap-import.md), per currency, not your revenue or bills of
materials.

For a scenario where the chosen suppliers are out for N weeks:

| Figure | Computed as |
|---|---|
| Purchase flow interrupted | 12-month spend × N / 52 |
| Covered by safety stock | the weeks of finished-goods stock the supplier stated, up to N |
| **At risk** | 12-month spend × (N − covered weeks) / 52 |

The safety-stock weeks come from the supplier's own answer in a
[supplier assessment](supplier-assessments.md) (the *Supply continuity* questionnaire),
labelled supplier-provided and not verified. A supplier without an answer counts as **0
weeks**, and the result says how many suppliers that applies to, so missing data is never
filled in with a guess.

Amounts are per currency and are **never converted or added together**. Suppliers and
mitigations are ranked by your main currency (the one on most purchase-order lines);
those without spend in it are listed after, not ranked.

## Who is out

All suppliers; suppliers based in, or with a site in, a country; chosen suppliers; or the
suppliers linked to a [war-room](war-room.md) incident. Over the API and
[MCP](mcp-server.md) also the suppliers matched by a public record.

## The resilience plan

For each supplier with spend at risk, two mitigations, each computed on its own against the
scenario and ranked by how much spend at risk it removes:

- **Raise safety stock** to T weeks (T defaults to N): removes 12-month spend × (uncovered
  weeks now − uncovered weeks with T) / 52.
- **Qualify a second source** for a share of the volume (50% by default): removes that share
  of the supplier's spend at risk. Suppliers that told you they rely on a single source or
  site are marked.

T and the share are the planner's assumptions: change them and run again. Every result lists
how it was computed.

## Saved scenarios

A saved scenario keeps its definition (who, how long, the assumptions), not its result: it
is recomputed from current spend and answers every time it is run.

API: `POST /api/v1/scenario-studio/run`, `GET/POST /api/v1/scenario-studio/saved`,
`GET /api/v1/scenario-studio/saved/{id}/run`, `DELETE /api/v1/scenario-studio/saved/{id}`.

The older *Simulator* page is a demonstration on sample data and stays behind
`SAMPLE_FEATURES`. Risk events no longer show an invented dollar impact: they show the
impacted suppliers' 12-month spend per currency.
