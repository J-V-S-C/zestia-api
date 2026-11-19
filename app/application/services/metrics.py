from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.application.entities import RequestStatus


@dataclass(frozen=True)
class RequestMetrics:
    total_requests: int
    requested_food_kg: Decimal
    approved_food_kg: Decimal
    pending_requests: int
    approved_requests: int
    rejected_requests: int


@dataclass(frozen=True)
class MetricsSummary:
    total_organizations: int
    registered_food_kg: Decimal
    requests: RequestMetrics


@dataclass(frozen=True)
class OrganizationMetrics:
    organization_id: UUID
    organization_name: str
    registered_food_kg: Decimal
    donation_requests: RequestMetrics
    recipient_requests: RequestMetrics


class MetricsRepository(Protocol):
    def metrics_summary(
        self, organization_id: UUID | None, status: RequestStatus | None
    ) -> MetricsSummary: ...
    def organization_metrics(
        self, organization_id: UUID | None, status: RequestStatus | None, offset: int, limit: int
    ) -> list[OrganizationMetrics]: ...


class MetricsService:
    def __init__(self, repository: MetricsRepository) -> None:
        self.repository = repository

    def summary(
        self, organization_id: UUID | None = None, status: RequestStatus | None = None
    ) -> MetricsSummary:
        return self.repository.metrics_summary(organization_id, status)

    def organizations(
        self, organization_id: UUID | None, status: RequestStatus | None, offset: int, limit: int
    ) -> list[OrganizationMetrics]:
        return self.repository.organization_metrics(organization_id, status, offset, limit)
