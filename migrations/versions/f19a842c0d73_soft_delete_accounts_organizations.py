"""Preserve accounts and organizations on deletion."""

import sqlalchemy as sa
from alembic import op

revision = "f19a842c0d73"
down_revision = "e407cb9265a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "organizations", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.drop_constraint("organizations_owner_account_id_key", "organizations", type_="unique")
    op.create_index(
        "organizations_active_owner_key",
        "organizations",
        ["owner_account_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    # Restoring one organization per account may conflict with archived replacements;
    # let PostgreSQL reject the downgrade rather than discard preserved records.
    op.drop_index("organizations_active_owner_key", table_name="organizations")
    op.create_unique_constraint(
        "organizations_owner_account_id_key", "organizations", ["owner_account_id"]
    )
    op.drop_column("organizations", "deleted_at")
    op.drop_column("accounts", "deleted_at")
