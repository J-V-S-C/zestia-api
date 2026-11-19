"""Enforce one admin identity; consolidate legacy admins with bootstrap first."""

from alembic import op
from sqlalchemy import text

revision = "c63d1f207a94"
down_revision = "b82c61394e0f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF (SELECT count(*) FROM accounts WHERE role = 'ADMIN') > 1 THEN
                RAISE EXCEPTION 'Multiple legacy admins exist'
                USING HINT = 'Run updated scripts/admin.py, then retry this migration.';
            END IF;
        END $$;
    """)
    op.create_index(
        "accounts_single_admin_key",
        "accounts",
        ["role"],
        unique=True,
        postgresql_where=text("role = 'ADMIN'"),
    )


def downgrade() -> None:
    op.drop_index("accounts_single_admin_key", table_name="accounts")
