from datetime import date
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.entities import Food, Organization, OrganizationType
from app.infrastructure.repository import SqlAlchemyRepository


def test_delete_does_not_misreport_unexpected_integrity_failure_as_dependency_conflict():
    session = Mock(spec=Session)
    error = IntegrityError("DELETE", {}, Exception("unexpected constraint failure"))
    session.flush.side_effect = error
    session.scalar.return_value = False
    organization = Organization(uuid4(), uuid4(), "NGO", OrganizationType.NGO, "Centro")
    with pytest.raises(IntegrityError) as raised:
        SqlAlchemyRepository(session).delete_organization(organization)
    assert raised.value is error


def test_food_delete_preserves_unexpected_integrity_errors():
    session = Mock(spec=Session)
    error = IntegrityError("DELETE", {}, Exception("unexpected constraint failure"))
    session.flush.side_effect = error
    food = Food(uuid4(), uuid4(), "Rice", "Grains", Decimal("1"), date.max)
    with pytest.raises(IntegrityError) as raised:
        SqlAlchemyRepository(session).delete_food(food)
    assert raised.value is error
