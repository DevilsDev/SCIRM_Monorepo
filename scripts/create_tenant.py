"""
Onboard a new customer: create the organization and an invitation for its first
administrator. The administrator opens the link, sets a name and password, and can
then invite their colleagues from Settings → Team.

Runs as the application role (DATABASE_URL, the same connection the services use).
The organization row needs no tenant context; the invitation is created inside the
new organization's row-level-security scope.

    python scripts/create_tenant.py --name "PharmaCorp International" --industry pharmaceutical \\
        --admin-email head.of.procurement@pharmacorp.com

In staging, run it inside a gateway pod, which has DATABASE_URL and PUBLIC_APP_URL:

    kubectl -n scirm-staging exec deploy/api-gateway -- python scripts/create_tenant.py ...

The printed link is a credential: send it to the administrator only, over a channel you
trust. It works once and expires (INVITATION_TTL_HOURS, default 7 days).
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from libs.common.store import EmailExists, PostgresStore  # noqa: E402

INDUSTRIES = ("pharmaceutical", "medical_devices", "biotech", "general")


async def create_tenant(database_url: str, name: str, industry: str, admin_email: str):
    store = PostgresStore(database_url)
    try:
        # Check first, so an existing account never leaves an empty organization behind.
        if await store.find_login_user(admin_email):
            raise EmailExists(admin_email)
        org_id = await store.create_organization(name, industry)
        invitation, token = await store.create_invitation(org_id, admin_email.strip().lower(), ["admin", "analyst"],
                                                          invited_by=None)
        return org_id, invitation, token
    finally:
        await store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True, help="organization name")
    parser.add_argument("--industry", default="general", choices=INDUSTRIES)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    try:
        org_id, invitation, token = asyncio.run(create_tenant(args.database_url, args.name, args.industry,
                                                              args.admin_email))
    except EmailExists:
        raise SystemExit(f"{args.admin_email} already has an account; no organization was created.")
    base = os.getenv("PUBLIC_APP_URL", "").rstrip("/")
    print(f"Organization: {args.name} ({org_id})")
    print(f"Administrator invitation for {invitation['email']}, expires {invitation['expires_at']}:")
    print(f"  {base}/invite#{token}" if base else f"  <app url>/invite#{token}")
    print("This link is a credential. Send it only to the administrator; it cannot be shown again.")


if __name__ == "__main__":
    main()
