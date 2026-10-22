# Two-step sign-in

Each user can add a second step to their sign-in: after the password, a 6-digit code from
an authenticator app (TOTP: Microsoft Authenticator, Google Authenticator, 1Password and
others).

## For users

**Settings → Two-step sign-in → Set up.** Scan the QR code or type the key into the app,
then enter the code it shows. Nothing changes until that code is accepted, so a mistyped
key cannot lock you out. The QR code is drawn in your browser; the key is not sent to any
other service.

To turn it off, enter a current code. Setting it up again while it is on is refused: turn
it off first. A stolen session alone can therefore neither remove nor replace your
authenticator.

## Lost phone

An administrator opens **Settings → Team** and chooses **Reset two-step sign-in** for that
person. They can then sign in with their password and set it up again. Administrators
cannot reset their own: they turn it off with a code like everyone else. Every enable,
disable and reset is written to the audit log (`mfa.enabled`, `mfa.disabled`,
`mfa.reset_by_admin`).

If the only administrator of an organization loses their phone, an operator clears it in
the database for that one account. Row-level security is forced on `users`, so set the
organization first (its id is in `organizations`), in one transaction:

```sql
BEGIN;
SELECT set_config('app.current_org_id', '<organization id>', true);
UPDATE users SET mfa_secret = NULL, mfa_enabled = false
 WHERE lower(email) = lower('admin@customer.com');  -- expect: UPDATE 1
COMMIT;
```

## Deployment settings

| Variable | Default | Meaning |
|---|---|---|
| `MFA_ENABLED` | `true` | Ask users who set up two-step sign-in for a code. `false` lets them sign in with a password alone (for an emergency, not normal use). |
| `MFA_ENCRYPTION_KEY` | required outside development | Encrypts the stored keys (AES-256-GCM). 32 random bytes, base64url: `python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('='))"` |

Codes are accepted for the current, previous and next 30-second period. Code attempts are
covered by the gateway's general rate limit (`RATE_LIMIT_PER_MINUTE`), not a per-account
lockout.
