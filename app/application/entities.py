from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.application.errors import InvalidInput


class AccountRole(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"


class VerificationStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"


class OrganizationType(StrEnum):
    SUPERMARKET = "SUPERMARKET"
    NGO = "NGO"
    COMMUNITY_KITCHEN = "COMMUNITY_KITCHEN"


class RequestStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class Organization:
    id: UUID
    owner_account_id: UUID
    name: str
    type: OrganizationType
    location: str
    deleted_at: datetime | None = None
    verification_status: VerificationStatus = VerificationStatus.PENDING

    def __post_init__(self) -> None:
        for name, maximum in (("name", 160), ("location", 240)):
            value = getattr(self, name).strip()
            if not value or len(value) > maximum:
                raise InvalidInput(
                    "invalid_organization", f"{name} must contain 1–{maximum} characters."
                )
            object.__setattr__(self, name, value)
        if not isinstance(self.type, OrganizationType):
            raise InvalidInput("invalid_organization_type", "Unsupported organization type.")


@dataclass(frozen=True)
class Account:
    id: UUID
    email: str
    password_hash: str = field(repr=False)
    deleted_at: datetime | None = None
    role: AccountRole = AccountRole.USER


@dataclass(frozen=True)
class Food:
    id: UUID
    donor_organization_id: UUID
    name: str
    category: str
    quantity_kg: Decimal
    expiration_date: date

    def __post_init__(self) -> None:
        for name, maximum in (("name", 160), ("category", 80)):
            value = getattr(self, name).strip()
            if not value or len(value) > maximum:
                raise InvalidInput("invalid_food", f"{name} must contain 1–{maximum} characters.")
            object.__setattr__(self, name, value)
        if (
            not self.quantity_kg.is_finite()
            or not Decimal("0") < self.quantity_kg <= Decimal("999999999.999")
            or self.quantity_kg != self.quantity_kg.quantize(Decimal("0.001"))
        ):
            raise InvalidInput(
                "invalid_food_quantity",
                "Quantity must be positive, at most 999999999.999 kg, with up to 3 decimal places.",
            )
        object.__setattr__(self, "quantity_kg", self.quantity_kg.quantize(Decimal("0.001")))


@dataclass(frozen=True)
class FoodRequest:
    id: UUID
    food_id: UUID
    donor_organization_id: UUID
    recipient_organization_id: UUID
    quantity_kg: Decimal
    status: RequestStatus
    created_at: datetime

    def __post_init__(self) -> None:
        if (
            not self.quantity_kg.is_finite()
            or not Decimal("0") < self.quantity_kg <= Decimal("999999999.999")
            or self.quantity_kg != self.quantity_kg.quantize(Decimal("0.001"))
        ):
            raise InvalidInput(
                "invalid_request_quantity",
                "Quantity must be positive, at most 999999999.999 kg, with up to 3 decimal places.",
            )
        object.__setattr__(self, "quantity_kg", self.quantity_kg.quantize(Decimal("0.001")))
        if not isinstance(self.status, RequestStatus):
            raise InvalidInput("invalid_request_status", "Unsupported request status.")
