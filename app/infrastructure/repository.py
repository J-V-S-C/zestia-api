from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.entities import Account, Food, Organization, OrganizationType
from app.application.errors import BusinessError, NotFound
from app.infrastructure.models import (
    AccountRecord,
    FoodRecord,
    FoodRequestRecord,
    OrganizationRecord,
)


def organization_from_record(record: OrganizationRecord) -> Organization:
    return Organization(
        record.id,
        record.owner_account_id,
        record.name,
        OrganizationType(record.type),
        record.location,
    )


class SqlAlchemyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_account(self, account_id: UUID) -> Account | None:
        record = self.session.scalar(
            select(AccountRecord)
            .where(AccountRecord.id == account_id, AccountRecord.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (
            Account(record.id, record.email, record.password_hash, record.deleted_at)
            if record
            else None
        )

    def find_account(self, email: str) -> Account | None:
        record = self.session.scalar(select(AccountRecord).where(AccountRecord.email == email))
        return (
            Account(record.id, record.email, record.password_hash, record.deleted_at)
            if record
            else None
        )

    def save_account(self, account: Account) -> None:
        self.session.add(AccountRecord(**asdict(account)))
        self.session.flush()

    def get_organization(self, organization_id: UUID, *, lock: bool = False) -> Organization:
        query = select(OrganizationRecord).where(
            OrganizationRecord.id == organization_id, OrganizationRecord.deleted_at.is_(None)
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        record = self.session.scalar(query)
        if record is None:
            raise NotFound("organization_not_found", "Organization does not exist.")
        return organization_from_record(record)

    def find_owned_organization(
        self, account_id: UUID, *, lock: bool = False
    ) -> Organization | None:
        query = select(OrganizationRecord).where(
            OrganizationRecord.owner_account_id == account_id,
            OrganizationRecord.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        record = self.session.scalar(query)
        return organization_from_record(record) if record else None

    def list_organizations(self, offset: int, limit: int) -> list[Organization]:
        records = self.session.scalars(
            select(OrganizationRecord)
            .where(OrganizationRecord.deleted_at.is_(None))
            .order_by(OrganizationRecord.name, OrganizationRecord.id)
            .offset(offset)
            .limit(limit)
        )
        return [organization_from_record(record) for record in records]

    def save_organization(self, organization: Organization) -> None:
        self.session.merge(OrganizationRecord(**asdict(organization)))
        self.session.flush()

    def delete_organization(self, organization: Organization) -> None:
        has_food = self.session.scalar(
            select(exists().where(FoodRecord.donor_organization_id == organization.id))
        )
        has_requests = self.session.scalar(
            select(exists().where(FoodRequestRecord.recipient_organization_id == organization.id))
        )
        if has_food or has_requests:
            raise BusinessError(
                "organization_in_use", "Organizations with associated records cannot be deleted."
            )
        record = self.session.get(OrganizationRecord, organization.id)
        record.deleted_at = datetime.now(UTC)
        self.session.flush()

    def delete_account(self, account_id: UUID) -> None:
        organization = self.find_owned_organization(account_id, lock=True)
        if organization is not None:
            self.delete_organization(organization)
        record = self.session.get(AccountRecord, account_id)
        record.deleted_at = datetime.now(UTC)
        self.session.flush()

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


def food_from_record(record: FoodRecord) -> Food:
    return Food(
        record.id,
        record.donor_organization_id,
        record.name,
        record.category,
        record.quantity_kg,
        record.expiration_date,
    )
