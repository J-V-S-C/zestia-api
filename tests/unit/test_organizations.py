from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.application.entities import Organization, OrganizationType
from app.application.errors import BusinessError, Forbidden, InvalidInput
from app.application.ports.repositories import OrganizationRepository
from app.application.services.organizations import OrganizationService


@pytest.mark.parametrize("type", list(OrganizationType))
def test_all_institution_types_can_be_registered(type: OrganizationType) -> None:
    repository = Mock(spec=OrganizationRepository)
    repository.find_owned_organization.return_value = None
    account_id = uuid4()
    organization = OrganizationService(repository).create(
        account_id, "  Kitchen  ", type, "  Porto Alegre  "
    )
    assert (organization.name, organization.location) == ("Kitchen", "Porto Alegre")
    assert organization.owner_account_id == account_id
    assert organization.type == type


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", " "),
        ("name", "x" * 161),
        ("location", " "),
        ("location", "x" * 241),
        ("type", "donor"),
    ],
)
def test_invalid_organizations_are_rejected(field: str, value: str) -> None:
    organization = Organization(uuid4(), uuid4(), "Market", OrganizationType.NGO, "Centro")
    with pytest.raises(InvalidInput):
        replace(organization, **{field: value})


def test_account_cannot_create_second_organization() -> None:
    repository = Mock(spec=OrganizationRepository)
    repository.find_owned_organization.return_value = Organization(
        uuid4(), uuid4(), "NGO", OrganizationType.NGO, "Centro"
    )
    with pytest.raises(BusinessError, match="only one"):
        OrganizationService(repository).create(uuid4(), "Other", OrganizationType.NGO, "Centro")
    repository.save_organization.assert_not_called()


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_non_owner_cannot_change_an_organization(operation: str) -> None:
    repository = Mock(spec=OrganizationRepository)
    organization = Organization(uuid4(), uuid4(), "NGO", OrganizationType.NGO, "Centro")
    repository.get_organization.return_value = organization
    service = OrganizationService(repository)
    with pytest.raises(Forbidden):
        if operation == "update":
            service.update(
                uuid4(), organization.id, "Changed", OrganizationType.SUPERMARKET, "Centro"
            )
        else:
            service.delete(uuid4(), organization.id)
    repository.save_organization.assert_not_called()
    repository.delete_organization.assert_not_called()


def test_owner_can_update_fields_without_changing_identity():
    repository = Mock(spec=OrganizationRepository)
    organization = Organization(uuid4(), uuid4(), "NGO", OrganizationType.NGO, "Centro")
    repository.get_organization.return_value = organization
    updated = OrganizationService(repository).update(
        organization.owner_account_id,
        organization.id,
        " New name ",
        OrganizationType.COMMUNITY_KITCHEN,
        " Floresta ",
    )
    assert (updated.id, updated.owner_account_id) == (
        organization.id,
        organization.owner_account_id,
    )
    assert (updated.name, updated.location, updated.type) == (
        "New name",
        "Floresta",
        OrganizationType.COMMUNITY_KITCHEN,
    )
    assert organization.name == "NGO"
    repository.save_organization.assert_called_once_with(updated)


def test_owner_can_delete_unused_organization():
    repository = Mock(spec=OrganizationRepository)
    organization = Organization(uuid4(), uuid4(), "NGO", OrganizationType.NGO, "Centro")
    repository.get_organization.return_value = organization
    OrganizationService(repository).delete(organization.owner_account_id, organization.id)
    repository.delete_organization.assert_called_once_with(organization)


def test_get_and_paginated_list_return_repository_results():
    repository = Mock(spec=OrganizationRepository)
    organization = Organization(uuid4(), uuid4(), "NGO", OrganizationType.NGO, "Centro")
    repository.get_organization.return_value = organization
    repository.list_organizations.return_value = [organization]
    service = OrganizationService(repository)
    assert service.get(organization.id) == organization
    assert service.list(2, 5) == [organization]
    repository.list_organizations.assert_called_once_with(2, 5)


@pytest.mark.parametrize("operation", ["get", "update", "delete"])
def test_missing_organization_is_reported_without_writes(operation):
    from app.application.errors import NotFound

    repository = Mock(spec=OrganizationRepository)
    repository.get_organization.side_effect = NotFound("organization_not_found", "Missing")
    service = OrganizationService(repository)
    with pytest.raises(NotFound):
        if operation == "get":
            service.get(uuid4())
        elif operation == "update":
            service.update(uuid4(), uuid4(), "Name", OrganizationType.NGO, "Centro")
        else:
            service.delete(uuid4(), uuid4())
    repository.save_organization.assert_not_called()
    repository.delete_organization.assert_not_called()


def test_invalid_update_preserves_existing_organization():
    repository = Mock(spec=OrganizationRepository)
    organization = Organization(uuid4(), uuid4(), "NGO", OrganizationType.NGO, "Centro")
    repository.get_organization.return_value = organization
    with pytest.raises(InvalidInput):
        OrganizationService(repository).update(
            organization.owner_account_id, organization.id, " ", OrganizationType.NGO, "Centro"
        )
    repository.save_organization.assert_not_called()
