from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from app.application.entities import (
    Food,
    FoodRequest,
    Organization,
    OrganizationType,
    RequestStatus,
    VerificationStatus,
)
from app.application.errors import BusinessError, Forbidden, InvalidInput
from app.application.ports.repositories import (
    FoodRepository,
    FoodRequestRepository,
    OrganizationRepository,
)
from app.application.services.requests import FoodRequestService


@pytest.fixture
def requests():
    repository = Mock(spec=FoodRequestRepository)
    foods = Mock(spec=FoodRepository)
    organizations = Mock(spec=OrganizationRepository)
    donor = Organization(
        uuid4(),
        uuid4(),
        "Donor",
        OrganizationType.SUPERMARKET,
        "Centro",
        verification_status=VerificationStatus.VERIFIED,
    )
    recipient = replace(donor, id=uuid4(), owner_account_id=uuid4(), name="Recipient")
    food = Food(uuid4(), donor.id, "Rice", "Grains", Decimal("10"), date.max)
    request = FoodRequest(
        uuid4(),
        food.id,
        donor.id,
        recipient.id,
        Decimal("6"),
        RequestStatus.PENDING,
        datetime.now(UTC),
    )
    foods.get_food.return_value = food
    foods.approved_food_quantity.return_value = Decimal("0")
    repository.get_food_request.return_value = request
    organizations.get_organization.return_value = donor
    organizations.find_owned_organization.return_value = recipient
    service = FoodRequestService(repository, foods, organizations)
    return service, repository, foods, organizations, food, donor, recipient, request


@pytest.mark.parametrize("type", list(OrganizationType))
def test_any_organization_type_can_request_without_reserving_food(requests, type):
    service, repository, foods, organizations, food, _, recipient, _ = requests
    organizations.find_owned_organization.return_value = replace(recipient, type=type)
    request = service.create(recipient.owner_account_id, food.id, Decimal("10"))
    assert request.status == RequestStatus.PENDING
    assert request.quantity_kg == Decimal("10.000")
    assert request.recipient_organization_id == recipient.id
    assert request.donor_organization_id == food.donor_organization_id
    assert request.created_at.utcoffset() is not None
    repository.save_food_request.assert_called_once_with(request)
    foods.save_food.assert_not_called()


@pytest.mark.parametrize(
    "quantity", ["0", "-1", "0.0001", "1000000000", "NaN", "Infinity", "-Infinity"]
)
def test_invalid_quantity_cannot_be_saved(requests, quantity):
    service, repository, _, _, food, _, recipient, _ = requests
    with pytest.raises(InvalidInput) as error:
        service.create(recipient.owner_account_id, food.id, Decimal(quantity))
    assert error.value.code == "invalid_request_quantity"
    repository.save_food_request.assert_not_called()


def test_invalid_status_is_rejected(requests):
    *_, request = requests
    with pytest.raises(InvalidInput):
        replace(request, status="DELIVERED")


def test_organization_required(requests):
    service, repository, _, organizations, food, _, recipient, _ = requests
    organizations.find_owned_organization.return_value = None
    with pytest.raises(Forbidden) as error:
        service.create(recipient.owner_account_id, food.id, Decimal("1"))
    assert error.value.code == "organization_required"
    repository.save_food_request.assert_not_called()


@pytest.mark.parametrize(
    "status",
    [VerificationStatus.PENDING, VerificationStatus.REJECTED, VerificationStatus.SUSPENDED],
)
@pytest.mark.parametrize("operation", ["create", "approve"])
def test_verification_required_for_participation(requests, status, operation):
    service, repository, _, organizations, food, donor, recipient, request = requests
    organizations.get_organization.return_value = replace(donor, verification_status=status)
    organizations.find_owned_organization.return_value = replace(
        recipient, verification_status=status
    )
    with pytest.raises(Forbidden) as error:
        if operation == "create":
            service.create(recipient.owner_account_id, food.id, Decimal("1"))
        else:
            service.approve(donor.owner_account_id, request.id)
    assert error.value.code == "organization_unverified"
    repository.save_food_request.assert_not_called()


def test_self_request_rejected(requests):
    service, repository, _, organizations, food, donor, _, _ = requests
    organizations.find_owned_organization.return_value = donor
    with pytest.raises(InvalidInput) as error:
        service.create(donor.owner_account_id, food.id, Decimal("1"))
    assert error.value.code == "own_food_request"
    repository.save_food_request.assert_not_called()


@pytest.mark.parametrize("operation", ["create", "approve"])
@pytest.mark.parametrize(
    "expiration,accepted", [(date(2026, 11, 16), False), (date(2026, 11, 17), True)]
)
def test_expiration_uses_sao_paulo_day(requests, operation, expiration, accepted):
    service, repository, foods, _, food, donor, recipient, request = requests
    foods.get_food.return_value = replace(food, expiration_date=expiration)
    instant = datetime(2026, 11, 18, 1, tzinfo=UTC)
    with patch("app.application.services.requests.datetime") as clock:
        clock.now.side_effect = lambda zone: instant.astimezone(zone)

        def perform():
            if operation == "create":
                return service.create(recipient.owner_account_id, food.id, Decimal("1"))
            return service.approve(donor.owner_account_id, request.id)

        if accepted:
            perform()
            repository.save_food_request.assert_called_once()
        else:
            with pytest.raises(InvalidInput) as error:
                perform()
            assert error.value.code == "food_expired"
            repository.save_food_request.assert_not_called()


@pytest.mark.parametrize("operation", ["create", "approve"])
def test_available_balance_is_rechecked(requests, operation):
    service, repository, foods, _, food, donor, recipient, request = requests
    foods.approved_food_quantity.return_value = Decimal("4.001")
    with pytest.raises(BusinessError) as error:
        if operation == "create":
            service.create(recipient.owner_account_id, food.id, Decimal("6"))
        else:
            service.approve(donor.owner_account_id, request.id)
    assert error.value.code == "insufficient_food"
    repository.save_food_request.assert_not_called()


@pytest.mark.parametrize("status", [RequestStatus.APPROVED, RequestStatus.REJECTED])
@pytest.mark.parametrize("operation", ["approve", "reject"])
def test_processed_request_cannot_change_status(requests, status, operation):
    service, repository, _, _, _, donor, _, request = requests
    repository.get_food_request.return_value = replace(request, status=status)
    with pytest.raises(BusinessError) as error:
        getattr(service, operation)(donor.owner_account_id, request.id)
    assert error.value.code == "request_already_processed"
    repository.save_food_request.assert_not_called()


@pytest.mark.parametrize("operation", ["approve", "reject"])
def test_only_donor_can_process(requests, operation):
    service, repository, _, _, _, _, recipient, request = requests
    with pytest.raises(Forbidden) as error:
        getattr(service, operation)(recipient.owner_account_id, request.id)
    assert error.value.code == "not_donor"
    repository.save_food_request.assert_not_called()


def test_approval_preserves_traceability_and_registered_quantity(requests):
    service, repository, foods, _, food, donor, _, request = requests
    foods.approved_food_quantity.return_value = Decimal("4")
    assert service.approve(donor.owner_account_id, request.id) == replace(
        request, status=RequestStatus.APPROVED
    )
    foods.save_food.assert_not_called()
    repository.save_food_request.assert_called_once_with(
        replace(request, status=RequestStatus.APPROVED)
    )
    assert food.quantity_kg == Decimal("10")


def test_rejection_allowed_for_expired_food_and_suspended_donor(requests):
    service, repository, foods, organizations, food, donor, _, request = requests
    foods.get_food.return_value = replace(food, expiration_date=date.min)
    organizations.get_organization.return_value = replace(
        donor, verification_status=VerificationStatus.SUSPENDED
    )
    assert service.reject(donor.owner_account_id, request.id).status == RequestStatus.REJECTED
    foods.approved_food_quantity.assert_not_called()
    repository.save_food_request.assert_called_once()


@pytest.mark.parametrize("participant", ["donor", "recipient", "outsider", "none"])
def test_history_access_is_limited_to_participants_without_verification_gate(requests, participant):
    service, _, _, organizations, _, donor, recipient, request = requests
    organization = {
        "donor": donor,
        "recipient": recipient,
        "outsider": replace(recipient, id=uuid4()),
        "none": None,
    }[participant]
    organizations.find_owned_organization.return_value = (
        replace(organization, verification_status=VerificationStatus.SUSPENDED)
        if organization
        else None
    )
    if participant in ("donor", "recipient"):
        assert service.get(uuid4(), request.id) == request
    else:
        with pytest.raises(Forbidden):
            service.get(uuid4(), request.id)


def test_account_without_organization_has_empty_history(requests):
    service, repository, _, organizations, *_ = requests
    organizations.find_owned_organization.return_value = None
    assert service.list(uuid4(), 0, 50) == []
    repository.list_food_requests.assert_not_called()
