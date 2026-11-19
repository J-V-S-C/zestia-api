from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.application.entities import RequestStatus
from app.infrastructure.http.authentication import AccountDependency
from app.infrastructure.http.dtos import (
    MetricsResponse,
    OrganizationMetricsResponse,
)
from app.infrastructure.http.providers import (
    MetricsDependency,
)

router = APIRouter()


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
