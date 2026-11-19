from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.infrastructure.http.authentication import AccountDependency
from app.infrastructure.http.dtos import (
    OrganizationInput,
    OrganizationResponse,
)
from app.infrastructure.http.providers import (
    OrganizationsDependency,
)

router = APIRouter()


@router.get(
    "/auth/me/organization",
    response_model=OrganizationResponse,
    tags=["organizations"],
    summary="Get the logged-in account's active organization",
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "The account has no active organization"},
    },
)
def own_organization(
    account: AccountDependency, service: OrganizationsDependency
) -> OrganizationResponse:
    return OrganizationResponse.model_validate(service.owned(account.id))


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


@router.get(
    "/auth/me/organizations/archived",
    response_model=list[OrganizationResponse],
    tags=["organizations"],
)
def archived_organizations(
    account: AccountDependency,
    service: OrganizationsDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return [
        OrganizationResponse.model_validate(item)
        for item in service.archived(account.id, offset, limit)
    ]
