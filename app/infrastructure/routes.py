from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.infrastructure.dependencies import (
    AccountDependency,
    AuthenticationDependency,
    OrganizationsDependency,
)
from app.infrastructure.schemas import (
    AccountResponse,
    LoginInput,
    OrganizationInput,
    OrganizationResponse,
    RegistrationInput,
    TokenResponse,
)

router = APIRouter(prefix="/api/v1")


@router.post("/auth/register", response_model=AccountResponse, status_code=201, tags=["auth"])
def register(payload: RegistrationInput, service: AuthenticationDependency) -> AccountResponse:
    return AccountResponse.model_validate(
        service.register(str(payload.email), payload.password.get_secret_value())
    )


@router.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(
    payload: LoginInput, service: AuthenticationDependency, request: Request
) -> TokenResponse:
    account = service.login(str(payload.email), payload.password.get_secret_value())
    return TokenResponse(
        access_token=request.app.state.tokens.issue(account.id),
        expires_in=request.app.state.settings.access_token_minutes * 60,
    )


@router.get("/auth/me", response_model=AccountResponse, tags=["auth"])
def me(account: AccountDependency) -> AccountResponse:
    return AccountResponse.model_validate(account)


@router.post(
    "/organizations", response_model=OrganizationResponse, status_code=201, tags=["organizations"]
)
def create_organization(
    payload: OrganizationInput,
    account: AccountDependency,
    service: OrganizationsDependency,
    response: Response,
) -> OrganizationResponse:
    organization = service.create(account.id, **payload.model_dump())
    response.headers["Location"] = f"/api/v1/organizations/{organization.id}"
    return OrganizationResponse.model_validate(organization)


@router.get("/organizations", response_model=list[OrganizationResponse], tags=["organizations"])
def list_organizations(
    account: AccountDependency,
    service: OrganizationsDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[OrganizationResponse]:
    return [OrganizationResponse.model_validate(item) for item in service.list(offset, limit)]


@router.get(
    "/organizations/{organization_id}", response_model=OrganizationResponse, tags=["organizations"]
)
def get_organization(
    organization_id: UUID, account: AccountDependency, service: OrganizationsDependency
) -> OrganizationResponse:
    return OrganizationResponse.model_validate(service.get(organization_id))


@router.put(
    "/organizations/{organization_id}", response_model=OrganizationResponse, tags=["organizations"]
)
def update_organization(
    organization_id: UUID,
    payload: OrganizationInput,
    account: AccountDependency,
    service: OrganizationsDependency,
) -> OrganizationResponse:
    return OrganizationResponse.model_validate(
        service.update(account.id, organization_id, **payload.model_dump())
    )


@router.delete("/organizations/{organization_id}", status_code=204, tags=["organizations"])
def delete_organization(
    organization_id: UUID, account: AccountDependency, service: OrganizationsDependency
) -> Response:
    service.delete(account.id, organization_id)
    return Response(status_code=204)
