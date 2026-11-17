from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AccountRecord(Base):
    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("email = lower(trim(email))", name="normalized_email"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrganizationRecord(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0 AND name = trim(name)", name="organization_name"),
        CheckConstraint(
            "length(trim(location)) > 0 AND location = trim(location)", name="organization_location"
        ),
        CheckConstraint(
            "type IN ('SUPERMARKET', 'NGO', 'COMMUNITY_KITCHEN')", name="organization_type"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(160))
    type: Mapped[str] = mapped_column(String(24))
    location: Mapped[str] = mapped_column(String(240))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index(
    "organizations_active_owner_key",
    OrganizationRecord.owner_account_id,
    unique=True,
    postgresql_where=text("deleted_at IS NULL"),
)


class FoodRecord(Base):
    __tablename__ = "foods"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0 AND name = trim(name)", name="food_name"),
        CheckConstraint(
            "length(trim(category)) > 0 AND category = trim(category)", name="food_category"
        ),
        CheckConstraint("quantity_kg > 0 AND quantity_kg <= 999999999.999", name="food_quantity"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    donor_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(80))
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    expiration_date: Mapped[date]


class FoodRequestRecord(Base):
    __tablename__ = "food_requests"
    __table_args__ = (
        CheckConstraint(
            "quantity_kg > 0 AND quantity_kg <= 999999999.999", name="food_request_quantity"
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')", name="food_request_status"
        ),
        Index("ix_food_requests_food_id_status", "food_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    food_id: Mapped[UUID] = mapped_column(ForeignKey("foods.id", ondelete="RESTRICT"))
    recipient_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
