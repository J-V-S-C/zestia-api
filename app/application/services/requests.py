from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.application.entities import (
    Food,
    FoodRequest,
    Organization,
    RequestStatus,
    VerificationStatus,
)
from app.application.errors import BusinessError, Forbidden, InvalidInput
from app.application.interfaces import FoodRepository, FoodRequestRepository, OrganizationRepository


class FoodRequestService:
    def __init__(
        self,
        repository: FoodRequestRepository,
        foods: FoodRepository,
        organizations: OrganizationRepository,
    ) -> None:
        self.repository = repository
        self.foods = foods
        self.organizations = organizations

    def create(self, account_id: UUID, food_id: UUID, quantity_kg: Decimal) -> FoodRequest:
        # Lock food before organizations, as in approval and food editing/deletion.
        food = self.foods.get_food(food_id, lock=True)
        recipient = self.organizations.find_owned_organization(account_id, lock=True)
        if recipient is None:
            raise Forbidden(
                "organization_required", "Register an organization before requesting food."
            )
        self._require_verified(recipient)
        if recipient.id == food.donor_organization_id:
            raise InvalidInput("own_food_request", "An organization cannot request its own food.")
        request = FoodRequest(
            uuid4(),
            food.id,
            food.donor_organization_id,
            recipient.id,
            quantity_kg,
            RequestStatus.PENDING,
            datetime.now(UTC),
        )
        self._require_unexpired(food)
        self._require_available(food, request.quantity_kg)
        self.repository.save_food_request(request)
        return request

    def get(self, account_id: UUID, request_id: UUID) -> FoodRequest:
        request = self.repository.get_food_request(request_id)
        organization = self.organizations.find_owned_organization(account_id)
        if organization is None or organization.id not in (
            request.donor_organization_id,
            request.recipient_organization_id,
        ):
            raise Forbidden(
                "request_access_denied", "Only participating organizations can view a request."
            )
        return request

    def list(
        self,
        account_id: UUID,
        offset: int,
        limit: int,
        status: RequestStatus | None = None,
        donor_organization_id: UUID | None = None,
        recipient_organization_id: UUID | None = None,
    ) -> list[FoodRequest]:
        organization = self.organizations.find_owned_organization(account_id)
        if organization is None:
            return []
        return self.repository.list_food_requests(
            organization.id, offset, limit, status, donor_organization_id, recipient_organization_id
        )

    def approve(self, account_id: UUID, request_id: UUID) -> FoodRequest:
        return self._process(account_id, request_id, RequestStatus.APPROVED)

    def reject(self, account_id: UUID, request_id: UUID) -> FoodRequest:
        return self._process(account_id, request_id, RequestStatus.REJECTED)

    def _process(self, account_id: UUID, request_id: UUID, status: RequestStatus) -> FoodRequest:
        request = self.repository.get_food_request(request_id)
        # All approvals and food quantity edits serialize on this same row.
        food = self.foods.get_food(request.food_id, lock=True)
        request = self.repository.get_food_request(request_id, lock=True)
        donor = self.organizations.get_organization(food.donor_organization_id, lock=True)
        if donor.owner_account_id != account_id:
            raise Forbidden("not_donor", "Only the donor organization owner can process requests.")
        if request.status != RequestStatus.PENDING:
            raise BusinessError(
                "request_already_processed", "Only pending requests can be processed."
            )
        if status == RequestStatus.APPROVED:
            self._require_verified(donor)
            self._require_unexpired(food)
            self._require_available(food, request.quantity_kg)
        updated = replace(request, status=status)
        self.repository.save_food_request(updated)
        return updated

    def _require_available(self, food: Food, quantity_kg: Decimal) -> None:
        available = food.quantity_kg - self.foods.approved_food_quantity(food.id)
        if quantity_kg > available:
            raise BusinessError(
                "insufficient_food", "Requested quantity exceeds currently available food."
            )

    @staticmethod
    def _require_unexpired(food: Food) -> None:
        if food.expiration_date < datetime.now(ZoneInfo("America/Sao_Paulo")).date():
            raise InvalidInput("food_expired", "Expired food cannot be requested or approved.")

    @staticmethod
    def _require_verified(organization: Organization) -> None:
        if organization.verification_status != VerificationStatus.VERIFIED:
            raise Forbidden(
                "organization_unverified",
                "Organization must be verified before requesting or approving food.",
            )
