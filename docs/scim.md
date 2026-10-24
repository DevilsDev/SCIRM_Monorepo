# User provisioning (SCIM)

Your identity provider (Microsoft Entra ID, Okta, OneLogin, …) can manage SCIRM accounts
with **SCIM 2.0**:
- creating them when someone is assigned the application
- updating names, emails and roles
- deactivating people who leave

Use it together with [single sign-on](single-sign-on.md). Accounts that SCIM creates have
no usable password: people sign in with SSO, or set a password with a reset link where
password sign-in is allowed.

## Setting up

In **Administration → Integrations → User provisioning (SCIM)**:
1. **Create SCIM token.** It is shown once and expires in a year.
2. In your identity provider's provisioning settings, enter:
   - **Tenant URL**: `<PUBLIC_API_URL>/scim/v2`, as shown on the card
   - **Secret token**: the token
3. Map the user's email to `userName`.

A SCIM token is an API key with the scope `scim`. It can call **only** `/scim/v2` (no
other part of the API), and read keys cannot call `/scim/v2`. It is listed with its last
use, and revoking it stops provisioning at the next request.

## What is supported

| | |
|---|---|
| `GET /Users` | Filters `userName eq "…"` and `externalId eq "…"`; paging with `startIndex` and `count` (up to 200). |
| `GET /Users/{id}` | |
| `POST /Users` | `userName` (the email, unique across SCIRM), `name` or `displayName`, `active`, `externalId`, `roles`. |
| `PUT /Users/{id}` | Replace the attributes above. |
| `PATCH /Users/{id}` | `add`/`replace` on `active`, `userName`, `name.*`, `displayName`, `externalId`, `roles`, the work email. Both forms identity providers use: with a `path`, and without one (a value object). `"True"`/`"False"` strings are accepted. |
| `DELETE /Users/{id}` | Deactivates (the account is kept for the audit trail). |
| `ServiceProviderConfig`, `ResourceTypes`, `Schemas` | |

**Roles** are SCIRM's: `admin`, `analyst`, `viewer`, `auditor` (as `roles: [{"value": "analyst"}]`).
Without roles, a new account is a `viewer`.

**Not supported:** groups (map roles to users instead), bulk operations, sorting, ETags,
`remove` operations, and changing passwords.

## Behaviour

- **Deactivating** (`active: false` or `DELETE`):
  - the person can no longer sign in, and their sessions cannot renew, so they end within
    60 minutes (the access token's lifetime)
  - reactivating restores access
- **The last active administrator** of an organization cannot be deactivated or demoted
  through SCIM (`409`, `scimType: mutability`), so the organization is never left without
  one.
- **Emails are unique across SCIRM.** Creating or renaming to an email used by any account,
  in any organization, returns `409` (`uniqueness`).
- **Errors** use the SCIM error format (`urn:ietf:params:scim:api:messages:2.0:Error`, with
  `status`, `scimType` and `detail`). Responses are `application/scim+json`.
- **Audit:** every request is recorded in the [audit log](audit-log.md) under *Access and
  team*, with the token as the actor (`api-key:<name> (<prefix>)`). Each change also gets
  its own entry naming the account (`userName`, roles, active): `scim.user_created`,
  `scim.user_updated`, `scim.user_deactivated` or `scim.user_reactivated`, with every
  changed field as `[before, after]`. A request that changes nothing adds no such entry.
