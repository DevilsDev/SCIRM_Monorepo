# Single sign-on

An organization can sign its members in through its own identity provider with
**OpenID Connect**: Microsoft Entra ID, Okta, Google Workspace, Keycloak, Auth0 and
others. The identity provider does the authentication, including its own two-step
sign-in; SCIRM's two-step sign-in is not asked for after single sign-on.

## Setting up

1. At the identity provider, create an application (a web app, confidential client) with
   the redirect URI shown in **Administration → Integrations → Single sign-on**. It is
   `<PUBLIC_API_URL>/api/v1/auth/sso/callback`.
2. In SCIRM, enter:
   - the **issuer**: your tenant-specific one, exactly as the provider states it (for
     Entra: `https://login.microsoftonline.com/<tenant id>/v2.0`)
   - the **client ID**
   - the **client secret**

   **Check and save** fetches the provider's metadata and refuses settings that do not
   match. The secret is stored encrypted and never shown again; leave it empty later to
   keep it.
3. Invite your members as usual. **SSO does not create accounts.** Someone without an
   active SCIRM account in your organization is refused after signing in at the provider.
   To provision them automatically, use [SCIM](scim.md). In an organization that requires single sign-on,
   accepting an invitation creates the account but does not sign the person in with the
   password; they continue with **Sign in with SSO**.

Members click **Sign in with SSO** on the sign-in page and enter their email. SCIRM finds
their account, sends them to their organization's identity provider, and back.

## Require single sign-on

With **Require single sign-on for members** on, members can no longer sign in, reset or
change a password in SCIRM. **Administrators keep their password** (with two-step sign-in)
so the organization is not locked out when the identity provider is down; give that role
to few people.

## How accounts are matched

- **The first SSO sign-in** links the account to the provider's subject (its stable user id)
  using the email in the ID token. That email must be verified (`email_verified` is not
  false) and belong to an active member of this organization.
- **After that** the subject must match. A different person who later gets the same email
  at the provider is refused, and a member whose email changes at the provider still gets
  in.
- **Moving to another identity provider** (a new issuer): members are linked again by
  verified email at their next sign-in. Within one issuer the subject never changes. The
  organization's administrators already decide which identity provider signs members in,
  so this gives them no new power.

## Security

- **Flow:** authorization code with PKCE (S256), `response_mode=query`, and a confidential
  client (HTTP Basic). State, nonce and the PKCE verifier sit in a signed, HttpOnly,
  SameSite=Lax cookie on the gateway for 10 minutes.
- **ID token checks:**
  - an asymmetric algorithm (RS, PS or ES), from a key in the provider's key set (fetched
    again once for an unknown key id)
  - issuer, audience (and `azp`), expiry within 60 s of leeway, and the nonce
- **Refused issuers:** multi-tenant issuers (Entra `/common`, `/organizations`,
  `/consumers`), because anyone can create a tenant there with any email.
- **Requests to the provider:** discovery, key set and token go through the same outbound
  guard as SAP and webhooks. Outside development that means https only, public addresses
  only, no redirects, short timeouts and small responses.
- **After the callback:** the browser gets a **one-time code in the URL fragment**, not
  tokens. It is valid for 60 seconds and works once; the app exchanges it at
  `/api/v1/auth/sso/exchange`.
- **The code only works in the tab that started the sign-in.** The login page keeps a random
  value in `sessionStorage` and sends only its SHA-256 to `/sso/start`. The exchange must
  present the value itself, and a wrong value leaves the code unused. So a code captured
  from someone's sign-in, or a sign-in an attacker starts in a victim's browser, cannot sign
  that browser into the attacker's account (login CSRF).
- **Audit log:** `auth.sso_login`, `auth.sso_login_failed` (with a reason code such as
  `bad_state`, `invalid_token`, `no_account`, `subject_mismatch`), `sso.configured` and
  `sso.removed`.

Asking to sign in with an email that has no account, or whose organization has no single
sign-on, gives the same answer. For an organization with single sign-on, the redirect to
its identity provider shows that the account exists, as with any SSO.

## Deployment

| Variable | |
|---|---|
| `PUBLIC_API_URL` | The gateway's public address (development default `http://localhost:8000`). The redirect URI is built from it, never from the request. |
| `PUBLIC_APP_URL` | The web app's address: where sign-in finishes. |

Without both, single sign-on is unavailable and the page says so.

Turning on **Require single sign-on** does not end members' existing sessions: a session
signed in with a password before it was turned on lasts until its refresh token expires (up
to 30 days).

For Microsoft Entra, add the optional `email` claim to the ID token (Token configuration).
Without it, first sign-ins are refused (`no_verified_email`).

## Not built yet

- Creating accounts at first sign-in: use [SCIM](scim.md) to provision them.
- Domain verification.
- Single logout. People disabled at the identity provider are deactivated through
  [SCIM](scim.md); their sessions then end within 60 minutes.
