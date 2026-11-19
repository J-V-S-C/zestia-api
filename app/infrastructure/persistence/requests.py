from dataclasses import asdict
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.entities import (
    FoodRequest,
    RequestStatus,
)
from app.application.errors import NotFound
from app.infrastructure.persistence.orm import (
    FoodRecord,
    FoodRequestRecord,
)


def request_from_record(record: FoodRequestRecord, donor_organization_id: UUID) -> FoodRequest:
    return FoodRequest(
        record.id,
        record.food_id,
        donor_organization_id,
        record.recipient_organization_id,
        record.quantity_kg,
        RequestStatus(record.status),
        record.created_at,
    )


class SqlAlchemyFoodRequestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save_food_request(self, request: FoodRequest) -> None:
        values = asdict(request)
        # Donor identity is derived from food, never duplicated in request storage.
        values.pop("donor_organization_id")
        self.session.merge(FoodRequestRecord(**values))
        self.session.flush()

    def get_food_request(self, request_id: UUID, *, lock: bool = False) -> FoodRequest:
        query = (
            select(FoodRequestRecord, FoodRecord.donor_organization_id)
            .join(FoodRecord, FoodRecord.id == FoodRequestRecord.food_id)
            .where(FoodRequestRecord.id == request_id)
        )
        if lock:
            query = query.with_for_update(of=FoodRequestRecord).execution_options(
                populate_existing=True
            )
        row = self.session.execute(query).one_or_none()
        if row is None:
            raise NotFound("request_not_found", "Request does not exist.")
        return request_from_record(*row)

    def list_food_requests(
        self,
        organization_id: UUID,
        offset: int,
        limit: int,
        status: RequestStatus | None = None,
        donor_organization_id: UUID | None = None,
        recipient_organization_id: UUID | None = None,
    ) -> list[FoodRequest]:
        query = (
            select(FoodRequestRecord, FoodRecord.donor_organization_id)
            .join(FoodRecord, FoodRecord.id == FoodRequestRecord.food_id)
            .where(
                or_(
                    FoodRecord.donor_organization_id == organization_id,
                    FoodRequestRecord.recipient_organization_id == organization_id,
                )
            )
        )
        if status is not None:
            query = query.where(FoodRequestRecord.status == status)
        if donor_organization_id is not None:
            query = query.where(FoodRecord.donor_organization_id == donor_organization_id)
        if recipient_organization_id is not None:
            query = query.where(
                FoodRequestRecord.recipient_organization_id == recipient_organization_id
            )
        rows = self.session.execute(
            query.order_by(FoodRequestRecord.created_at, FoodRequestRecord.id)
            .offset(offset)
            .limit(limit)
        )
        return [request_from_record(*row) for row in rows]
