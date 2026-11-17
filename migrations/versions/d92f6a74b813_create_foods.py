"""Create food listings.

Revision ID: d92f6a74b813
Revises: c831a3bf245a
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d92f6a74b813"
down_revision: str | Sequence[str] | None = "c831a3bf245a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "foods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("donor_organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("quantity_kg", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("expiration_date", sa.Date(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0 AND name = trim(name)", name="food_name"),
        sa.CheckConstraint(
            "length(trim(category)) > 0 AND category = trim(category)", name="food_category"
        ),
        sa.CheckConstraint(
            "quantity_kg > 0 AND quantity_kg <= 999999999.999", name="food_quantity"
        ),
        sa.ForeignKeyConstraint(
            ["donor_organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_foods_donor_organization_id", "foods", ["donor_organization_id"])


def downgrade() -> None:
    op.drop_index("ix_foods_donor_organization_id", table_name="foods")
    op.drop_table("foods")
