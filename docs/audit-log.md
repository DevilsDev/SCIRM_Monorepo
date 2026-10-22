# Audit log

Every sign-in and every change in an organization is recorded in its audit log:
- who did it (email, or "not signed in")
- what (a named action such as `mfa.enabled`, or the API route, for example `PATCH /api/v1/org/members/{member_id}`)
- when (UTC)
- the result (HTTP status)
- the client address

Reads are not recorded, except exports of the log itself.

The log is **append-only**: PostgreSQL triggers refuse `UPDATE`, `DELETE` and `TRUNCATE`
on `audit_logs` (migration 009), and row-level security limits each organization to its
own entries.

## The screen

**Administration → Audit log**, for administrators and auditors.

| Filter | Matches |
|---|---|
| Sign-ins | `auth.*`: sign-ins and failed sign-ins |
| Access and team | two-step sign-in, invitations, roles and deactivation (`mfa.*`, `invitation.*`, `/org/*`, `/auth/*`) |
| Integrations and imports | the SAP connection and every supplier or spend import |
| Data changes | everything else |
| Person | part of the email |
| From / To | calendar days in your time zone |
| Failed or refused only | status 400 or higher |

A wrong password for an existing account appears in that account's organization, as a
failed sign-in with the client address. Attempts on emails that have no account belong to
no organization and do not appear.

Click an entry for its details. **Load older entries** pages back through the log.

## Export

**Export CSV** downloads the entries that match the current filters, newest first, up to
50,000 rows (`AUDIT_EXPORT_MAX`); narrow the dates to export more. The export is itself
recorded as `audit.exported`.

Times are in UTC (`created_at_utc`). Cells that a spreadsheet would treat as a formula
(starting with `=`, `+`, `-` or `@`) are prefixed with `'`.

API: `GET /api/v1/audit` (filters `category`, `actor`, `failed`, `since`, `until`; paging
`limit`, `before` = the previous page's `next_cursor`) and `GET /api/v1/audit/export`.
