from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.application.entities import Food, Organization, OrganizationType, VerificationStatus
from app.application.errors import BusinessError, Forbidden, InvalidInput, NotFound
from app.application.interfaces import FoodRepository, OrganizationRepository
from app.application.services.foods import FoodService


@pytest.fixture
def foods():
    repository = Mock(spec=FoodRepository)
    organizations = Mock(spec=OrganizationRepository)
    return FoodService(repository, organizations), repository, organizations


@pytest.mark.parametrize("type", list(OrganizationType))
def test_any_organization_type_can_register_food(foods, type):
    service, repository, organizations = foods
    organization = Organization(
        uuid4(),
        uuid4(),
        "Kitchen",
        type,
        "Porto Alegre",
        verification_status=VerificationStatus.VERIFIED,
    )
    organizations.find_owned_organization.return_value = organization
    food = service.create(
        organization.owner_account_id, " Rice ", " Grains ", Decimal("1.125"), date.max
    )
    assert (food.name, food.category) == ("Rice", "Grains")
    assert food.donor_organization_id == organization.id
    assert food.quantity_kg == Decimal("1.125")
    repository.save_food.assert_called_once_with(food)


def test_account_without_organization_cannot_donate(foods):
    service, repository, organizations = foods
    organizations.find_owned_organization.return_value = None
    with pytest.raises(Forbidden) as error:
        service.create(uuid4(), "Rice", "Grains", Decimal("1"), date.max)
    assert error.value.code == "organization_required"
    repository.save_food.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", " "),
        ("name", "x" * 161),
        ("category", " "),
        ("category", "x" * 81),
        ("quantity_kg", Decimal("0")),
        ("quantity_kg", Decimal("-0.001")),
        ("quantity_kg", Decimal("0.0001")),
        ("quantity_kg", Decimal("1000000000")),
        ("quantity_kg", Decimal("NaN")),
        ("quantity_kg", Decimal("Infinity")),
        ("quantity_kg", Decimal("-Infinity")),
    ],
)
def test_invalid_food_is_rejected_before_save(foods, field, value):
    service, repository, organizations = foods
    organizations.find_owned_organization.return_value = Organization(
        uuid4(),
        uuid4(),
        "Kitchen",
        OrganizationType.NGO,
        "Centro",
        verification_status=VerificationStatus.VERIFIED,
    )
    fields = {
        "name": "Rice",
        "category": "Grains",
        "quantity_kg": Decimal("1"),
        "expiration_date": date.max,
        field: value,
    }
    with pytest.raises(InvalidInput):
        service.create(uuid4(), **fields)
    repository.save_food.assert_not_called()


@pytest.mark.parametrize(
    "expiration,accepted", [(date(2026, 11, 16), False), (date(2026, 11, 17), True)]
)
def test_expiration_uses_sao_paulo_date_at_utc_midnight(foods, expiration, accepted):
    service, repository, organizations = foods
    organizations.find_owned_organization.return_value = Organization(
        uuid4(),
        uuid4(),
        "Kitchen",
        OrganizationType.NGO,
        "Centro",
        verification_status=VerificationStatus.VERIFIED,
    )
    instant = datetime(2026, 11, 18, 1, tzinfo=UTC)
    with patch("app.application.services.foods.datetime") as clock:
        clock.now.side_effect = lambda zone: instant.astimezone(zone)
        if accepted:
            service.create(uuid4(), "Rice", "Grains", Decimal("0.001"), expiration)
            repository.save_food.assert_called_once()
        else:
            with pytest.raises(InvalidInput) as error:
                service.create(uuid4(), "Rice", "Grains", Decimal("1"), expiration)
            assert error.value.code == "food_expired"
            repository.save_food.assert_not_called()
        clock.now.assert_called_once_with(ZoneInfo("America/Sao_Paulo"))


def test_expired_food_can_still_be_read_for_history(foods):
    service, repository, _ = foods
    food = Food(uuid4(), uuid4(), "Rice", "Grains", Decimal("999999999.999"), date.min)
    repository.get_food.return_value = food
    repository.list_foods.return_value = [food]
    assert service.get(food.id) == food
    assert service.list(2, 5) == [food]
    repository.list_foods.assert_called_once_with(2, 5, None)
    assert replace(food, quantity_kg=Decimal("0.001")).quantity_kg == Decimal("0.001")


def test_missing_food_is_reported(foods):
    service, repository, _ = foods
    repository.get_food.side_effect = NotFound("food_not_found", "Missing")
    with pytest.raises(NotFound):
        service.get(uuid4())


@pytest.fixture
def owned_food(foods):
    _, repository, organizations = foods
    donor = Organization(
        uuid4(),
        uuid4(),
        "Kitchen",
        OrganizationType.NGO,
        "Centro",
        verification_status=VerificationStatus.VERIFIED,
    )
    food = Food(uuid4(), donor.id, "Rice", "Grains", Decimal("10"), date.max)
    repository.get_food.return_value = food
    repository.approved_food_quantity.return_value = Decimal("0")
    organizations.get_organization.return_value = donor
    return food, donor


def test_owner_can_update_food_without_changing_identity(foods, owned_food):
    service, repository, _ = foods
    original, donor = owned_food
    updated = service.update(
        donor.owner_account_id, original.id, " Beans ", " Legumes ", Decimal("4.125"), date.max
    )
    assert updated == replace(
        original, name="Beans", category="Legumes", quantity_kg=Decimal("4.125")
    )
    assert original.name == "Rice"
    repository.save_food.assert_called_once_with(updated)


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_non_owner_cannot_modify_food(foods, owned_food, operation):
    service, repository, _ = foods
    food, _ = owned_food
    with pytest.raises(Forbidden) as error:
        if operation == "update":
            service.update(uuid4(), food.id, "Beans", "Grains", Decimal("1"), date.max)
        else:
            service.delete(uuid4(), food.id)
    assert error.value.code == "not_owner"
    repository.save_food.assert_not_called()
    repository.delete_food.assert_not_called()


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_missing_food_cannot_be_modified(foods, operation):
    service, repository, _ = foods
    repository.get_food.side_effect = NotFound("food_not_found", "Missing")
    with pytest.raises(NotFound):
        if operation == "update":
            service.update(uuid4(), uuid4(), "Rice", "Grains", Decimal("1"), date.max)
        else:
            service.delete(uuid4(), uuid4())
    repository.save_food.assert_not_called()
    repository.delete_food.assert_not_called()


@pytest.mark.parametrize("quantity", ["3.999", "4", "4.001"])
def test_update_cannot_reduce_quantity_below_approved_total(foods, owned_food, quantity):
    service, repository, _ = foods
    food, donor = owned_food
    repository.approved_food_quantity.return_value = Decimal("4")
    if Decimal(quantity) < Decimal("4"):
        with pytest.raises(BusinessError) as error:
            service.update(
                donor.owner_account_id, food.id, "Rice", "Grains", Decimal(quantity), date.max
            )
        assert error.value.code == "food_quantity_below_approved"
        repository.save_food.assert_not_called()
    else:
        assert service.update(
            donor.owner_account_id, food.id, "Rice", "Grains", Decimal(quantity), date.max
        ).quantity_kg == Decimal(quantity)


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"category": " "},
        {"quantity_kg": Decimal("0")},
        {"quantity_kg": Decimal("0.0001")},
        {"expiration_date": date.min},
    ],
)
def test_invalid_update_preserves_original_food(foods, owned_food, changes):
    service, repository, _ = foods
    food, donor = owned_food
    fields = {
        "name": food.name,
        "category": food.category,
        "quantity_kg": food.quantity_kg,
        "expiration_date": food.expiration_date,
        **changes,
    }
    with pytest.raises(InvalidInput):
        service.update(donor.owner_account_id, food.id, **fields)
    repository.save_food.assert_not_called()


def test_owner_can_delete_expired_unused_food(foods, owned_food):
    service, repository, _ = foods
    food, donor = owned_food
    repository.get_food.return_value = replace(food, expiration_date=date.min)
    service.delete(donor.owner_account_id, food.id)
    repository.delete_food.assert_called_once_with(replace(food, expiration_date=date.min))


def test_list_can_filter_by_donor(foods):
    service, repository, _ = foods
    donor_id = uuid4()
    repository.list_foods.return_value = []
    assert service.list(0, 50, donor_id) == []
    repository.list_foods.assert_called_once_with(0, 50, donor_id)
