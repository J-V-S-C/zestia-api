from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, StringConstraints

from app.application.entities import OrganizationType


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class OrganizationInput(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    type: OrganizationType
    location: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


class OrganizationResponse(OrganizationInput):
    id: UUID


class RegistrationInput(Schema):
    email: EmailStr
    password: SecretStr = Field(min_length=8, max_length=128)


class LoginInput(Schema):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)


class AccountResponse(Schema):
    id: UUID
    email: str


class TokenResponse(Schema):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
