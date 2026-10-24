# War room

Coordinate the response to a supply disruption in one place: who owns it, which suppliers
are affected and how much spend is at stake, what has to be done by whom, and a shared
timeline of everything that happened.

**Intelligence → War room.** Everyone in the organization can read incidents;
administrators and analysts open and work them.

## Opening an incident

- **From a public record:** **Open in war room** on a record in the Intel feed or on
  Regulatory watch. The record's title, source, link and date are copied into the incident
  (it keeps them even if the record is later withdrawn), its severity becomes the incident's,
  and the suppliers the record matches are linked: suppliers it names (confidence 0.6 or
  more, as for webhooks) and suppliers whose sites are exposed to a disaster alert.
- **By hand:** **Open an incident** with a title, a severity and an optional summary, for
  disruptions no public record covers (a strike, a supplier's call, a quality failure).

## Working it

- **Status:** open → monitoring → resolved (with an optional resolution), and back.
- **Owner** and **task assignees** must be active members of the organization.
- **Affected suppliers:** link or unlink any of your suppliers, with a reason.
- **Spend at stake:** the linked suppliers' 12-month spend (from the SAP spend import),
  **totalled per currency**. Amounts in different currencies are never converted or added
  together; suppliers without spend data are counted separately.
- **Tasks** with an assignee and a due date, ticked off when done.
- **Timeline:** notes, plus an automatic entry for every change (status, owner, severity,
  suppliers, tasks). It is append-only: the database refuses to change or delete entries,
  and incidents themselves cannot be deleted (which would take their timeline with them);
  an incident that is over is resolved, and can be reopened.

The page refreshes every 30 seconds, so several people can work on an incident at once.

## Audit and data

`incident.opened` and `incident.status_changed` are recorded by name in the
[audit log](audit-log.md), and every change by its request. Incidents, their suppliers,
tasks and timeline are tenant data with forced row-level security; a task or a linked
supplier can only belong to an incident (and a supplier) of the same organization.

API: `GET/POST /api/v1/incidents`, `GET/PATCH /api/v1/incidents/{id}`,
`POST …/notes`, `POST …/suppliers`, `DELETE …/suppliers/{supplier_id}`, `POST …/tasks`,
`PATCH …/tasks/{task_id}`.
