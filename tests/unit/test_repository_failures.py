from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.entities import Organization, OrganizationType
from app.infrastructure.repository import SqlAlchemyRepository


def test_delete_does_not_misreport_unexpected_integrity_failure_as_dependency_conflict():
    session = Mock(spec=Session)
    error = IntegrityError("DELETE", {}, Exception("unexpected constraint failure"))
    session.flush.side_effect = error
    organization = Organization(uuid4(), uuid4(), "NGO", OrganizationType.NGO, "Centro")
    with pytest.raises(IntegrityError) as raised:
        SqlAlchemyRepository(session).delete_organization(organization)
    assert raised.value is error
