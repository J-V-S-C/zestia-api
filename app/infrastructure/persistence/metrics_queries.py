from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from app.application.entities import RequestStatus
from app.application.query_results import MetricsSummary, OrganizationMetrics, RequestMetrics
from app.infrastructure.persistence.orm import FoodRecord, FoodRequestRecord, OrganizationRecord


def request_aggregates(status: RequestStatus | None) -> Select:
    query = select(
        func.count(FoodRequestRecord.id).label("total_requests"),
        func.coalesce(func.sum(FoodRequestRecord.quantity_kg), 0).label("requested_food_kg"),
        func.coalesce(
            func.sum(FoodRequestRecord.quantity_kg).filter(
                FoodRequestRecord.status == RequestStatus.APPROVED
            ),
            0,
        ).label("approved_food_kg"),
        func.count()
        .filter(FoodRequestRecord.status == RequestStatus.PENDING)
        .label("pending_requests"),
        func.count()
        .filter(FoodRequestRecord.status == RequestStatus.APPROVED)
        .label("approved_requests"),
        func.count()
        .filter(FoodRequestRecord.status == RequestStatus.REJECTED)
        .label("rejected_requests"),
    ).join(FoodRecord, FoodRecord.id == FoodRequestRecord.food_id)
    if status is not None:
        query = query.where(FoodRequestRecord.status == status)
    return query


def requests_from_row(row: RowMapping, prefix: str = "") -> RequestMetrics:
    return RequestMetrics(
        total_requests=row[f"{prefix}total_requests"],
        requested_food_kg=Decimal(row[f"{prefix}requested_food_kg"]).quantize(Decimal("0.001")),
        approved_food_kg=Decimal(row[f"{prefix}approved_food_kg"]).quantize(Decimal("0.001")),
        pending_requests=row[f"{prefix}pending_requests"],
        approved_requests=row[f"{prefix}approved_requests"],
        rejected_requests=row[f"{prefix}rejected_requests"],
    )


class SqlAlchemyMetricsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def metrics_summary(
        self, organization_id: UUID | None, status: RequestStatus | None
    ) -> MetricsSummary:
        organizations = select(func.count(OrganizationRecord.id)).where(
            OrganizationRecord.deleted_at.is_(None)
        )
        foods = select(func.coalesce(func.sum(FoodRecord.quantity_kg), 0))
        requests = request_aggregates(status)
        if organization_id is not None:
            organizations = organizations.where(OrganizationRecord.id == organization_id)
            foods = foods.where(FoodRecord.donor_organization_id == organization_id)
            requests = requests.where(
                or_(
                    FoodRecord.donor_organization_id == organization_id,
                    FoodRequestRecord.recipient_organization_id == organization_id,
                )
            )
        request_totals = requests.subquery()
        # One SQL statement gives counts and quantities the same committed snapshot.
        row = (
            self.session.execute(
                select(
                    organizations.scalar_subquery().label("total_organizations"),
                    foods.scalar_subquery().label("registered_food_kg"),
                    *request_totals.c,
                )
            )
            .mappings()
            .one()
        )
        return MetricsSummary(
            row["total_organizations"],
            Decimal(row["registered_food_kg"]).quantize(Decimal("0.001")),
            requests_from_row(row),
        )

    def organization_metrics(
        self, organization_id: UUID | None, status: RequestStatus | None, offset: int, limit: int
    ) -> list[OrganizationMetrics]:
        # Aggregate each relationship before joining, avoiding food/request fan-out.
        foods = (
            select(
                FoodRecord.donor_organization_id.label("organization_id"),
                func.sum(FoodRecord.quantity_kg).label("registered_food_kg"),
            )
            .group_by(FoodRecord.donor_organization_id)
            .subquery()
        )
        donations = (
            request_aggregates(status)
            .add_columns(FoodRecord.donor_organization_id.label("organization_id"))
            .group_by(FoodRecord.donor_organization_id)
            .subquery()
        )
        recipients = (
            request_aggregates(status)
            .add_columns(FoodRequestRecord.recipient_organization_id.label("organization_id"))
            .group_by(FoodRequestRecord.recipient_organization_id)
            .subquery()
        )
        columns = [
            OrganizationRecord.id.label("organization_id"),
            OrganizationRecord.name.label("organization_name"),
            func.coalesce(foods.c.registered_food_kg, 0).label("registered_food_kg"),
        ]
        for prefix, aggregate in (("donation_", donations), ("recipient_", recipients)):
            columns.extend(
                func.coalesce(column, 0).label(prefix + column.name)
                for column in aggregate.c
                if column.name != "organization_id"
            )
        query = (
            select(*columns)
            .select_from(OrganizationRecord)
            .outerjoin(foods, foods.c.organization_id == OrganizationRecord.id)
            .outerjoin(donations, donations.c.organization_id == OrganizationRecord.id)
            .outerjoin(recipients, recipients.c.organization_id == OrganizationRecord.id)
            .where(OrganizationRecord.deleted_at.is_(None))
        )
        if organization_id is not None:
            query = query.where(OrganizationRecord.id == organization_id)
        rows = self.session.execute(
            query.order_by(OrganizationRecord.name, OrganizationRecord.id)
            .offset(offset)
            .limit(limit)
        ).mappings()
        return [
            OrganizationMetrics(
                row["organization_id"],
                row["organization_name"],
                Decimal(row["registered_food_kg"]).quantize(Decimal("0.001")),
                requests_from_row(row, "donation_"),
                requests_from_row(row, "recipient_"),
            )
            for row in rows
        ]
