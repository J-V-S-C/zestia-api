from uuid import UUID

from app.application.entities import RequestStatus
from app.application.ports.repositories import MetricsRepository
from app.application.query_results import MetricsSummary, OrganizationMetrics


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
