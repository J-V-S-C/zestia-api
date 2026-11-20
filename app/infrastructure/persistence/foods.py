from dataclasses import asdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.entities import (
    Food,
)
from app.application.errors import BusinessError, NotFound
from app.infrastructure.persistence.orm import (
    FoodRecord,
    FoodRequestRecord,
)


def food_from_record(record: FoodRecord) -> Food:
    return Food(
        record.id,
        record.donor_organization_id,
        record.name,
        record.category,
        record.quantity_kg,
        record.expiration_date,
    )


class SqlAlchemyFoodRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save_food(self, food: Food) -> None:
        self.session.merge(FoodRecord(**asdict(food)))
        self.session.flush()

    def get_food(self, food_id: UUID, *, lock: bool = False) -> Food:
        query = select(FoodRecord).where(FoodRecord.id == food_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        record = self.session.scalar(query)
        if record is None:
            raise NotFound("food_not_found", "Food does not exist.")
        return food_from_record(record)

    def list_foods(
        self, offset: int, limit: int, donor_organization_id: UUID | None = None
    ) -> list[Food]:
        query = select(FoodRecord)
        if donor_organization_id is not None:
            query = query.where(FoodRecord.donor_organization_id == donor_organization_id)
        records = self.session.scalars(
            query.order_by(FoodRecord.name, FoodRecord.id).offset(offset).limit(limit)
        )
        return [food_from_record(record) for record in records]

    def approved_food_quantity(self, food_id: UUID) -> Decimal:
        return self.session.scalar(
            select(func.coalesce(func.sum(FoodRequestRecord.quantity_kg), 0)).where(
                FoodRequestRecord.food_id == food_id, FoodRequestRecord.status == "APPROVED"
            )
        )

    def food_has_requests(self, food_id: UUID) -> bool:
        return self.session.scalar(
            select(
                select(FoodRequestRecord.id).where(FoodRequestRecord.food_id == food_id).exists()
            )
        )

    def delete_food(self, food: Food) -> None:
        record = self.session.get(FoodRecord, food.id)
        self.session.delete(record)
        try:
            self.session.flush()
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == "23503":
                raise BusinessError(
                    "food_in_use", "Food with associated requests cannot be deleted."
                ) from error
            raise
