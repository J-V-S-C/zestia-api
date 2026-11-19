"""Replace reviewer flag with explicit account roles, preserving existing permissions."""

import sqlalchemy as sa
from alembic import op

revision = "ab74ce0389d2"
down_revision = "fc1916210037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts", sa.Column("role", sa.String(16), server_default="USER", nullable=False)
    )
    op.execute("UPDATE accounts SET role = 'REVIEWER' WHERE is_reviewer = true")
    op.create_check_constraint("account_role", "accounts", "role IN ('USER', 'REVIEWER')")
    op.drop_column("accounts", "is_reviewer")


def downgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("is_reviewer", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute("UPDATE accounts SET is_reviewer = true WHERE role = 'REVIEWER'")
    op.drop_constraint("account_role", "accounts", type_="check")
    op.drop_column("accounts", "role")
