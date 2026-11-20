from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.infrastructure.http.authentication import AccountDependency
from app.infrastructure.http.dtos import (
    FoodAvailabilityResponse,
    FoodInput,
    FoodResponse,
)
from app.infrastructure.http.providers import (
    FoodsDependency,
)

router = APIRouter()


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


@router.get(
    "/foods/{food_id}/availability", response_model=FoodAvailabilityResponse, tags=["foods"]
)
def food_availability(
    food_id: UUID, account: AccountDependency, service: FoodsDependency
) -> FoodAvailabilityResponse:
    return FoodAvailabilityResponse.model_validate(service.availability(food_id))
