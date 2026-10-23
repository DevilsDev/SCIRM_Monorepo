# Passwords

**Change password** (Settings) checks the current password and stores the new one with
bcrypt. Your other sessions are signed out; the one you are using continues.

**Forgot password** emails a reset link. The link:
- works **once**, for **30 minutes** (`PASSWORD_RESET_MINUTES`)
- stops working when a newer one is requested

SCIRM stores only a hash of the link's token. The token travels in the URL fragment
(`/reset-password#…`), so it is never sent to a server in a URL or a Referer header. The
answer is the same whether or not an account exists, and the email is sent in the
background, so neither the answer nor its timing reveals which emails have accounts.

Resetting signs out every session for that account: refresh tokens issued before the
change are refused (`users.password_changed_at`). An access token already issued keeps
working until it expires, at most 60 minutes.

Password reset needs [email](scheduled-reports.md#email-settings). Without `SMTP_HOST`,
the forgot-password page says that reset by email is not set up and to ask an
administrator.

Requests, resets and changes are recorded in the [audit log](audit-log.md)
(`auth.password_reset_requested`, `auth.password_reset`, `POST /api/v1/auth/change-password`).

Two-step sign-in, when on, is still asked for after a reset: a reset changes only the
password. See [Two-step sign-in](two-step-sign-in.md) for a lost phone.
