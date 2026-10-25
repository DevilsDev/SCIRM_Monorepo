# Public API

Other systems (BI tools, a data warehouse, an ERP) can read SCIRM data with an API key.
The API is **read-only**.

## Keys

An administrator creates keys in **Administration → Integrations → API keys**, with a name and an expiry (30
days, 90 days, 1 year or never).
- **Shown once.** The key is shown only when it is created; SCIRM stores only its SHA-256
  hash.
- **Owned by the organization.** A key belongs to the organization, not to the person who
  created it, so it keeps working if they leave. Their email is shown as its creator.
- **Revoking takes effect at once.** The next request with the key fails.

Each key is listed by its prefix (`scirm_` and 8 characters) with its last use. Creating
and revoking keys, and every refused request made with one of your keys (a route it may
not call, or the key after it expired or was revoked), are recorded in the
[audit log](audit-log.md) under *Access and team*, with the key's prefix, never the key.
A request with a key that matches no key at all (mistyped or made up) cannot be tied to
an organization, so it is refused (`401`) without appearing in anyone's audit log.
Successful reads are not recorded, like other reads.

Other kinds of key: a SCIM token ([user provisioning](scim.md)) and an MCP key
([AI agents](mcp-server.md)), each limited to its own part of the API.

## Calling the API

Send the key as a bearer token, or in `X-API-Key`:

```bash
curl -H "Authorization: Bearer scirm_AbCd1234_..." https://<your SCIRM>/api/v1/suppliers
```

| Method | Path | Returns |
|---|---|---|
| GET | `/api/v1/suppliers` | suppliers (with SAP number, sites, 12-month spend) |
| GET | `/api/v1/suppliers/{supplier_id}` | one supplier |
| GET | `/api/v1/suppliers/{supplier_id}/signals` | public records matched to it, and disaster exposure |
| GET | `/api/v1/signals/suppliers` | per supplier: number of public events, worst severity, Watch flag |
| GET | `/api/v1/alerts` | alerts |
| GET | `/api/v1/risks`, `/api/v1/risks/{risk_id}` | risks |
| GET | `/api/v1/intelligence/feed`, `/api/v1/intelligence/sources` | the public-record feed and its sources |
| GET | `/api/v1/export/suppliers` | suppliers as CSV |

The full request and response formats are in the OpenAPI specification (`openapi.json`).

## Errors

| Status | Meaning |
|---|---|
| 401 | The key is unknown, expired or revoked. |
| 403 | The key is valid, but the route is not one of the above. Keys cannot change data, see the team, read the audit log or change integrations. |
| 429 | Rate limit: requests per client address per minute (`RATE_LIMIT_PER_MINUTE`, default 100). |

## How it works

Behind the scenes, the gateway accepts a key only for the routes in the table. It checks
the exact method and route, so `POST /api/v1/suppliers/{id}/ask` is refused although
`GET /api/v1/suppliers/{id}` is allowed. For an allowed request, it swaps the key for a
one-minute internal token with the read-only *viewer* role in the key's organization, so
the usual tenant isolation and role checks apply unchanged.
