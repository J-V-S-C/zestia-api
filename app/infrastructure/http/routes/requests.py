from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.application.entities import RequestStatus
from app.infrastructure.http.authentication import AccountDependency
from app.infrastructure.http.dtos import (
    FoodRequestInput,
    FoodRequestResponse,
)
from app.infrastructure.http.providers import (
    RequestsDependency,
)

router = APIRouter()


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
