from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, StringConstraints

from app.application.entities import (
    AccountRole,
    OrganizationType,
    RequestStatus,
    VerificationStatus,
)


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class OrganizationInput(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    type: OrganizationType
    location: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


class OrganizationResponse(OrganizationInput):
    id: UUID
    verification_status: VerificationStatus
    deleted_at: datetime | None


class FoodInput(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    quantity_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    expiration_date: date


class FoodResponse(FoodInput):
    id: UUID
    donor_organization_id: UUID


class FoodRequestInput(Schema):
    food_id: UUID
    quantity_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class FoodRequestResponse(FoodRequestInput):
    id: UUID
    donor_organization_id: UUID
    recipient_organization_id: UUID
    status: RequestStatus
    created_at: datetime


class RegistrationInput(Schema):
    email: EmailStr
    password: SecretStr = Field(min_length=8, max_length=128)


class LoginInput(Schema):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)


class AccountResponse(Schema):
    id: UUID
    email: str
    role: AccountRole


class TokenResponse(Schema):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class RequestMetricsResponse(Schema):
    total_requests: int
    requested_food_kg: Decimal
    approved_food_kg: Decimal
    pending_requests: int
    approved_requests: int
    rejected_requests: int


class MetricsResponse(Schema):
    total_organizations: int
    registered_food_kg: Decimal
    requests: RequestMetricsResponse


class OrganizationMetricsResponse(Schema):
    organization_id: UUID
    organization_name: str
    registered_food_kg: Decimal
    donation_requests: RequestMetricsResponse
    recipient_requests: RequestMetricsResponse


class RecoveryRequest(Schema):
    email: EmailStr


class RecoveryConfirmation(Schema):
    token: SecretStr = Field(min_length=1, max_length=256)


class VerificationSubmission(Schema):
    evidence: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=20, max_length=1000)
    ]


class VerificationDecision(Schema):
    status: VerificationStatus
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
