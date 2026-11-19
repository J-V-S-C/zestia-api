from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


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
