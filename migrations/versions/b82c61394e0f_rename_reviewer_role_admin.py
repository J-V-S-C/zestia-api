"""Rename the privileged account role to ADMIN without changing permissions."""

from alembic import op

revision = "b82c61394e0f"
down_revision = "ab74ce0389d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("account_role", "accounts", type_="check")
    op.execute("UPDATE accounts SET role = 'ADMIN' WHERE role = 'REVIEWER'")
    op.create_check_constraint("account_role", "accounts", "role IN ('USER', 'ADMIN')")


def downgrade() -> None:
    op.drop_constraint("account_role", "accounts", type_="check")
    op.execute("UPDATE accounts SET role = 'REVIEWER' WHERE role = 'ADMIN'")
    op.create_check_constraint("account_role", "accounts", "role IN ('USER', 'REVIEWER')")
