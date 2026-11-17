from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.application.entities import Food
from app.application.errors import BusinessError, Forbidden, InvalidInput
from app.application.interfaces import FoodRepository, OrganizationRepository


class FoodService:
    def __init__(self, repository: FoodRepository, organizations: OrganizationRepository) -> None:
        self.repository = repository
        self.organizations = organizations

    def create(
        self,
        account_id: UUID,
        name: str,
        category: str,
        quantity_kg: Decimal,
        expiration_date: date,
    ) -> Food:
        organization = self.organizations.find_owned_organization(account_id, lock=True)
        if organization is None:
            raise Forbidden(
                "organization_required", "Register an organization before donating food."
            )
        food = Food(uuid4(), organization.id, name, category, quantity_kg, expiration_date)
        self._require_unexpired(food)
        self.repository.save_food(food)
        return food

    def get(self, food_id: UUID) -> Food:
        return self.repository.get_food(food_id)

    def list(
        self, offset: int, limit: int, donor_organization_id: UUID | None = None
    ) -> list[Food]:
        return self.repository.list_foods(offset, limit, donor_organization_id)

    def update(
        self,
        account_id: UUID,
        food_id: UUID,
        name: str,
        category: str,
        quantity_kg: Decimal,
        expiration_date: date,
    ) -> Food:
        food = self.repository.get_food(food_id, lock=True)
        self._require_owner(account_id, food)
        updated = replace(
            food,
            name=name,
            category=category,
            quantity_kg=quantity_kg,
            expiration_date=expiration_date,
        )
        self._require_unexpired(updated)
        if updated.quantity_kg < self.repository.approved_food_quantity(food.id):
            raise BusinessError(
                "food_quantity_below_approved",
                "Quantity cannot be reduced below the total already approved.",
            )
        self.repository.save_food(updated)
        return updated

    def delete(self, account_id: UUID, food_id: UUID) -> None:
        food = self.repository.get_food(food_id, lock=True)
        self._require_owner(account_id, food)
        self.repository.delete_food(food)

    def _require_owner(self, account_id: UUID, food: Food) -> None:
        organization = self.organizations.get_organization(food.donor_organization_id)
        if account_id != organization.owner_account_id:
            raise Forbidden(
                "not_owner", "Only the donor organization owner can change or delete food."
            )

    @staticmethod
    def _require_unexpired(food: Food) -> None:
        if food.expiration_date < datetime.now(ZoneInfo("America/Sao_Paulo")).date():
            raise InvalidInput("food_expired", "Expiration date must be today or later.")
