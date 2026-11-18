import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import AdminBootstrapSettings
from app.infrastructure.models import AccountRecord
from scripts.admin import provision_admin

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


def bootstrap_settings(password="operator-test-password"):
    return AdminBootstrapSettings(
        _env_file=None, admin_email="operator@example.com", admin_password=password
    )


def test_env_bootstrap_creates_hashed_admin_and_login_reports_role(client, database):
    settings = bootstrap_settings()
    with Session(database) as session, session.begin():
        provision_admin(session, settings)
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": str(settings.admin_email),
            "password": settings.admin_password.get_secret_value(),
        },
    )
    assert response.status_code == 200
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "ADMIN"
    with database.connect() as connection:
        password_hash = connection.scalar(text("SELECT password_hash FROM accounts"))
        assert password_hash.startswith("$argon2id$")
        assert settings.admin_password.get_secret_value() not in password_hash
    with Session(database) as session, session.begin():
        provision_admin(session, settings)
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM accounts")) == 1
        assert connection.scalar(text("SELECT count(*) FROM lifecycle_events")) == 1
    with Session(database) as session, session.begin():
        provision_admin(session, settings, revoke=True)
    assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "USER"
    assert (
        client.get(
            "/api/v1/organizations/00000000-0000-0000-0000-000000000000/verification",
            headers=headers,
        ).status_code
        == 403
    )


def test_signup_cannot_choose_privileged_role(client):
    body = {"email": "normal@example.com", "password": "password8"}
    assert client.post("/api/v1/auth/register", json={**body, "role": "ADMIN"}).status_code == 422
    registered = client.post("/api/v1/auth/register", json=body)
    assert registered.status_code == 201
    assert registered.json()["role"] == "USER"


@pytest.mark.parametrize("closed", [False, True])
def test_bootstrap_never_overwrites_existing_credentials_or_reopens_closed_account(
    client, database, closed
):
    body = {"email": "operator@example.com", "password": "existing-password"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 201
    with database.begin() as connection:
        if closed:
            connection.execute(text("UPDATE accounts SET deleted_at = now()"))
        original_hash = connection.scalar(text("SELECT password_hash FROM accounts"))
    with pytest.raises(ValueError), Session(database) as session, session.begin():
        provision_admin(session, bootstrap_settings())
    with Session(database) as session:
        account = session.scalar(select(AccountRecord))
        assert account.password_hash == original_hash
        assert account.role == "USER"
        assert (account.deleted_at is not None) == closed
