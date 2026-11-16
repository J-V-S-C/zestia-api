from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from app.application.errors import InvalidInput


class OrganizationType(StrEnum):
    SUPERMARKET = "SUPERMARKET"
    NGO = "NGO"
    COMMUNITY_KITCHEN = "COMMUNITY_KITCHEN"


@dataclass(frozen=True)
class Organization:
    id: UUID
    owner_account_id: UUID
    name: str
    type: OrganizationType
    location: str

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
