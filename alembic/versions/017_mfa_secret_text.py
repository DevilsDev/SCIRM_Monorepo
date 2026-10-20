"""Widen users.mfa_secret for encrypted values.

TOTP seeds are now stored encrypted (libs/common/secret_box.py: AES-256-GCM, about
90 characters), which does not fit the original varchar(64). Existing plaintext seeds
are re-encrypted by the application the first time each is read.

Revision ID: 017
Revises: 016
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN mfa_secret TYPE text")


def downgrade() -> None:
    # Encrypted values do not fit varchar(64); they are cleared, so affected users set up MFA again.
    op.execute("UPDATE users SET mfa_secret = NULL, mfa_enabled = false WHERE length(mfa_secret) > 64")
    op.execute("ALTER TABLE users ALTER COLUMN mfa_secret TYPE varchar(64)")
