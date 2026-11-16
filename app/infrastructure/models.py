from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AccountRecord(Base):
    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("email = lower(trim(email))", name="normalized_email"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))


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
    owner_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), unique=True
    )
    name: Mapped[str] = mapped_column(String(160))
    type: Mapped[str] = mapped_column(String(24))
    location: Mapped[str] = mapped_column(String(240))
