"""Add request records for food history and approved quantity constraints.

Revision ID: e407cb9265a1
Revises: d92f6a74b813
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e407cb9265a1"
down_revision: str | Sequence[str] | None = "d92f6a74b813"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "food_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("food_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_organization_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_kg", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "quantity_kg > 0 AND quantity_kg <= 999999999.999", name="food_request_quantity"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')", name="food_request_status"
        ),
        sa.ForeignKeyConstraint(["food_id"], ["foods.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["recipient_organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_food_requests_food_id_status", "food_requests", ["food_id", "status"])
    op.create_index(
        "ix_food_requests_recipient_organization_id", "food_requests", ["recipient_organization_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_food_requests_recipient_organization_id", table_name="food_requests")
    op.drop_index("ix_food_requests_food_id_status", table_name="food_requests")
    op.drop_table("food_requests")
