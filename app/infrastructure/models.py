from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AccountRecord(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("email = lower(trim(email))", name="normalized_email"),
        CheckConstraint("role IN ('USER', 'ADMIN')", name="account_role"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(16), server_default="USER")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RateLimitRecord(Base):
    __tablename__ = "recovery_rate_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int]
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecoveryRecord(Base):
    __tablename__ = "account_recovery"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LifecycleEventRecord(Base):
    __tablename__ = "lifecycle_events"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthSessionRecord(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrganizationRecord(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0 AND name = trim(name)", name="organization_name"),
        CheckConstraint(
            "length(trim(location)) > 0 AND location = trim(location)", name="organization_location"
        ),
        CheckConstraint(
            "verification_status IN ('PENDING', 'VERIFIED', 'REJECTED', 'SUSPENDED')",
            name="organization_verification_status",
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
    verification_status: Mapped[str] = mapped_column(String(16), server_default="PENDING")
    verification_evidence: Mapped[str | None] = mapped_column(String(1000))
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
