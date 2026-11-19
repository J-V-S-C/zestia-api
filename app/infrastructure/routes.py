from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials

from app.application.entities import RequestStatus
from app.application.errors import Unauthenticated
from app.infrastructure.dependencies import (
    AccountDependency,
    AuthenticationDependency,
    FoodsDependency,
    MetricsDependency,
    OrganizationsDependency,
    RepositoryDependency,
    RequestsDependency,
    bearer,
)
from app.infrastructure.schemas import (
    AccountResponse,
    FoodInput,
    FoodRequestInput,
    FoodRequestResponse,
    FoodResponse,
    LoginInput,
    MetricsResponse,
    OrganizationInput,
    OrganizationMetricsResponse,
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
    payload: LoginInput,
    service: AuthenticationDependency,
    request: Request,
    repository: RepositoryDependency,
) -> TokenResponse:
    account = service.login(str(payload.email), payload.password.get_secret_value())
    if repository.get_account(account.id) is None:
        raise Unauthenticated("invalid_credentials", "Email or password is incorrect.")
    token = request.app.state.tokens.issue(account.id)
    repository.save_session(
        account.id,
        token,
        datetime.now(UTC) + timedelta(minutes=request.app.state.settings.access_token_minutes),
    )
    return TokenResponse(
        access_token=token,
        expires_in=request.app.state.settings.access_token_minutes * 60,
    )


@router.post("/auth/logout", status_code=204, tags=["auth"])
def logout(
    account: AccountDependency,
    repository: RepositoryDependency,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> Response:
    repository.revoke_session(credentials.credentials)
    return Response(status_code=204)


@router.get("/auth/me", response_model=AccountResponse, tags=["auth"])
def me(account: AccountDependency) -> AccountResponse:
    return AccountResponse.model_validate(account)


@router.delete("/auth/me", status_code=204, tags=["auth"])
def close_account(account: AccountDependency, service: AuthenticationDependency) -> Response:
    service.close(account.id)
    return Response(status_code=204)


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


@router.post(
    "/organizations/{organization_id}/restore",
    response_model=OrganizationResponse,
    tags=["organizations"],
)
def restore_organization(
    organization_id: UUID, account: AccountDependency, service: OrganizationsDependency
) -> OrganizationResponse:
    return OrganizationResponse.model_validate(service.restore(account.id, organization_id))


@router.post("/foods", response_model=FoodResponse, status_code=201, tags=["foods"])
def create_food(
    payload: FoodInput,
    account: AccountDependency,
    service: FoodsDependency,
    response: Response,
) -> FoodResponse:
    food = service.create(account.id, **payload.model_dump())
    response.headers["Location"] = f"/api/v1/foods/{food.id}"
    return FoodResponse.model_validate(food)


@router.get("/foods", response_model=list[FoodResponse], tags=["foods"])
def list_foods(
    account: AccountDependency,
    service: FoodsDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    donor_organization_id: UUID | None = None,
) -> list[FoodResponse]:
    return [
        FoodResponse.model_validate(item)
        for item in service.list(offset, limit, donor_organization_id)
    ]


@router.get("/foods/{food_id}", response_model=FoodResponse, tags=["foods"])
def get_food(food_id: UUID, account: AccountDependency, service: FoodsDependency) -> FoodResponse:
    return FoodResponse.model_validate(service.get(food_id))


@router.put("/foods/{food_id}", response_model=FoodResponse, tags=["foods"])
def update_food(
    food_id: UUID,
    payload: FoodInput,
    account: AccountDependency,
    service: FoodsDependency,
) -> FoodResponse:
    return FoodResponse.model_validate(service.update(account.id, food_id, **payload.model_dump()))


@router.delete("/foods/{food_id}", status_code=204, tags=["foods"])
def delete_food(food_id: UUID, account: AccountDependency, service: FoodsDependency) -> Response:
    service.delete(account.id, food_id)
    return Response(status_code=204)


@router.post("/requests", response_model=FoodRequestResponse, status_code=201, tags=["requests"])
def create_request(
    payload: FoodRequestInput,
    account: AccountDependency,
    service: RequestsDependency,
    response: Response,
) -> FoodRequestResponse:
    request = service.create(account.id, **payload.model_dump())
    response.headers["Location"] = f"/api/v1/requests/{request.id}"
    return FoodRequestResponse.model_validate(request)


@router.get("/requests", response_model=list[FoodRequestResponse], tags=["requests"])
def list_requests(
    account: AccountDependency,
    service: RequestsDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status: RequestStatus | None = None,
    donor_organization_id: UUID | None = None,
    recipient_organization_id: UUID | None = None,
) -> list[FoodRequestResponse]:
    return [
        FoodRequestResponse.model_validate(item)
        for item in service.list(
            account.id, offset, limit, status, donor_organization_id, recipient_organization_id
        )
    ]


@router.get("/requests/{request_id}", response_model=FoodRequestResponse, tags=["requests"])
def get_request(
    request_id: UUID, account: AccountDependency, service: RequestsDependency
) -> FoodRequestResponse:
    return FoodRequestResponse.model_validate(service.get(account.id, request_id))


@router.post(
    "/requests/{request_id}/approve", response_model=FoodRequestResponse, tags=["requests"]
)
def approve_request(
    request_id: UUID, account: AccountDependency, service: RequestsDependency
) -> FoodRequestResponse:
    return FoodRequestResponse.model_validate(service.approve(account.id, request_id))


@router.post("/requests/{request_id}/reject", response_model=FoodRequestResponse, tags=["requests"])
def reject_request(
    request_id: UUID, account: AccountDependency, service: RequestsDependency
) -> FoodRequestResponse:
    return FoodRequestResponse.model_validate(service.reject(account.id, request_id))


@router.get("/metrics", response_model=MetricsResponse, tags=["metrics"])
def metrics(
    account: AccountDependency,
    service: MetricsDependency,
    organization_id: UUID | None = None,
    status: RequestStatus | None = None,
) -> MetricsResponse:
    return MetricsResponse.model_validate(service.summary(organization_id, status))


@router.get(
    "/metrics/organizations", response_model=list[OrganizationMetricsResponse], tags=["metrics"]
)
def organization_metrics(
    account: AccountDependency,
    service: MetricsDependency,
    organization_id: UUID | None = None,
    status: RequestStatus | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[OrganizationMetricsResponse]:
    return [
        OrganizationMetricsResponse.model_validate(item)
        for item in service.organizations(organization_id, status, offset, limit)
    ]
