from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.application.entities import Account
from app.application.errors import BusinessError, InvalidInput, Unauthenticated
from app.application.ports.repositories import AccountRepository, OrganizationRepository
from app.application.ports.security import PasswordHasher
from app.application.services.auth import AuthenticationService


@pytest.fixture
def auth():
    repository = Mock(spec=AccountRepository)
    repository.find_account.return_value = None
    hasher = Mock(spec=PasswordHasher)
    hasher.hash.return_value = "hashed-password"
    organizations = Mock(spec=OrganizationRepository)
    organizations.find_owned_organization.return_value = None
    return (
        AuthenticationService(repository, hasher, "admin@example.com", organizations),
        repository,
        hasher,
    )


@pytest.mark.parametrize("email", ["admin@example.com", "ADMIN@EXAMPLE.COM", " Admin@Example.com "])
@pytest.mark.parametrize("password", ["admin-bootstrap-password", "different-password"])
def test_reserved_admin_email_cannot_register_before_bootstrap(auth, email, password):
    service, repository, hasher = auth
    with pytest.raises(BusinessError) as error:
        service.register(email, password)
    assert error.value.code == "email_unavailable"
    repository.find_account.assert_not_called()
    repository.save_account.assert_not_called()
    hasher.hash.assert_not_called()


def test_reservation_normalizes_configured_admin_email(auth):
    _, repository, hasher = auth
    service = AuthenticationService(
        repository, hasher, " ADMIN@Example.COM ", Mock(spec=OrganizationRepository)
    )
    with pytest.raises(BusinessError):
        service.register("admin@example.com", "password8")
    repository.save_account.assert_not_called()


def test_reserved_admin_can_still_log_in_with_stored_credentials(auth):
    service, repository, hasher = auth
    account = Account(uuid4(), "admin@example.com", "stored-hash")
    repository.find_account.return_value = account
    hasher.verify.return_value = True
    assert service.login("ADMIN@example.com", "password8") == account


@pytest.mark.parametrize("length", [8, 128])
def test_registration_normalizes_email_and_persists_only_hash(auth, length):
    service, repository, hasher = auth
    password = "x" * length
    account = service.register("  OWNER@Example.COM ", password)
    assert account.email == "owner@example.com"
    assert account.password_hash == "hashed-password"
    repository.save_account.assert_called_once_with(account)
    hasher.hash.assert_called_once_with(password)
    assert password not in repr(account)


@pytest.mark.parametrize("length", [0, 7, 129])
def test_invalid_password_does_not_write_or_hash(auth, length):
    service, repository, hasher = auth
    with pytest.raises(InvalidInput) as error:
        service.register("owner@example.com", "x" * length)
    assert error.value.code == "invalid_password"
    hasher.hash.assert_not_called()
    repository.save_account.assert_not_called()


def test_duplicate_registration_does_not_replace_existing_password(auth):
    service, repository, hasher = auth
    repository.find_account.return_value = Account(uuid4(), "owner@example.com", "existing-hash")
    with pytest.raises(BusinessError) as error:
        service.register("OWNER@example.com", "a-long-password")
    assert error.value.code == "email_registered"
    repository.save_account.assert_not_called()
    hasher.hash.assert_not_called()


def test_login_returns_stored_account_with_normalized_lookup(auth):
    service, repository, hasher = auth
    account = Account(uuid4(), "owner@example.com", "stored-hash")
    repository.find_account.return_value = account
    hasher.verify.return_value = True
    assert service.login(" OWNER@EXAMPLE.COM ", "password") == account
    repository.find_account.assert_called_once_with("owner@example.com")
    hasher.verify.assert_called_once_with("password", "stored-hash")
    repository.save_account.assert_not_called()


@pytest.mark.parametrize("exists", [False, True])
def test_wrong_password_and_unknown_email_have_same_error(auth, exists):
    service, repository, hasher = auth
    repository.find_account.return_value = (
        Account(uuid4(), "owner@example.com", "stored-hash") if exists else None
    )
    hasher.verify.return_value = False
    with pytest.raises(Unauthenticated) as error:
        service.login("owner@example.com", "wrong")
    assert error.value.code == "invalid_credentials"
    hasher.verify.assert_called_once_with("wrong", "stored-hash" if exists else None)
    repository.save_account.assert_not_called()
