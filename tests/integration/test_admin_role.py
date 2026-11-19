from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.errors import InvalidInput
from app.config import AdminBootstrapSettings
from app.infrastructure.persistence.accounts import SqlAlchemyAccountRepository
from app.infrastructure.persistence.orm import AccountRecord, RecoveryRecord
from scripts.admin import provision_admin

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


def bootstrap_settings(password="operator-test-password", *, email="operator@example.com"):
    return AdminBootstrapSettings(_env_file=None, admin_email=email, admin_password=password)


def admin_login(client, settings):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": str(settings.admin_email),
            "password": settings.admin_password.get_secret_value(),
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_new_bootstrap_identity_closes_old_admin_and_preserves_linked_history(client, database):
    original = bootstrap_settings()
    with Session(database) as session, session.begin():
        provision_admin(session, original)
    old_headers = admin_login(client, original)
    other_old_headers = admin_login(client, original)
    old_account = client.get("/api/v1/auth/me", headers=old_headers).json()
    organization = client.post(
        "/api/v1/organizations",
        headers=old_headers,
        json={"name": "Admin history fixture", "type": "NGO", "location": "Centro"},
    )
    assert organization.status_code == 201
    with database.connect() as connection:
        original_hash = connection.scalar(text("SELECT password_hash FROM accounts"))

    replacement = bootstrap_settings("replacement-test-password", email="replacement@example.com")
    with Session(database) as session, session.begin():
        provision_admin(session, replacement)
    new_headers = admin_login(client, replacement)
    new_account = client.get("/api/v1/auth/me", headers=new_headers).json()
    assert new_account["role"] == "ADMIN"
    assert new_account["id"] != old_account["id"]
    assert client.get("/api/v1/auth/me", headers=old_headers).status_code == 401
    assert client.get("/api/v1/auth/me", headers=other_old_headers).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "operator@example.com", "password": "operator-test-password"},
        ).status_code
        == 401
    )
    with Session(database) as session:
        old = session.get(AccountRecord, old_account["id"])
        assert old.password_hash == original_hash
        assert old.deleted_at is not None
        assert old.role == "USER"
        assert session.scalar(text("SELECT count(*) FROM accounts")) == 2
        assert (
            str(session.scalar(text("SELECT owner_account_id FROM organizations")))
            == old_account["id"]
        )

    review_path = f"/api/v1/organizations/{organization.json()['id']}/verification"
    assert client.get(review_path, headers=old_headers).status_code == 401
    assert client.get(review_path, headers=new_headers).status_code == 200
    with database.connect() as connection:
        events = connection.execute(
            text(
                "SELECT account_id, action, reason FROM lifecycle_events "
                "WHERE action LIKE 'ADMIN_%' ORDER BY created_at, id"
            )
        ).all()
        assert {(str(event.account_id), event.action) for event in events} == {
            (old_account["id"], "ADMIN_GRANTED"),
            (new_account["id"], "ADMIN_GRANTED"),
            (old_account["id"], "ADMIN_RETIRED"),
        }
        assert len(events) == 3
        assert all(
            original.admin_password.get_secret_value() not in event.reason for event in events
        )
        assert all(
            replacement.admin_password.get_secret_value() not in event.reason for event in events
        )
        assert connection.scalar(text("SELECT count(*) FROM accounts")) == 2
        assert connection.scalar(text("SELECT count(*) FROM accounts WHERE role = 'ADMIN'")) == 1
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM auth_sessions "
                    "WHERE account_id = :id AND revoked_at IS NULL"
                ),
                {"id": old_account["id"]},
            )
            == 0
        )


def test_repeat_bootstrap_preserves_identity_hash_sessions_and_single_audit_event(client, database):
    settings = bootstrap_settings()
    with Session(database) as session, session.begin():
        provision_admin(session, settings)
    headers = admin_login(client, settings)
    original = client.get("/api/v1/auth/me", headers=headers).json()
    with database.connect() as connection:
        original_hash = connection.scalar(text("SELECT password_hash FROM accounts"))
    with Session(database) as session, session.begin():
        provision_admin(session, bootstrap_settings(email="OPERATOR@EXAMPLE.COM"))
    assert client.get("/api/v1/auth/me", headers=headers).json() == original
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM accounts")) == 1
        assert connection.scalar(text("SELECT password_hash FROM accounts")) == original_hash
        assert connection.scalar(text("SELECT count(*) FROM lifecycle_events")) == 1


def test_configured_password_rotation_revokes_old_sessions_and_preserves_admin_identity(
    client, database
):
    original = bootstrap_settings()
    with Session(database) as session, session.begin():
        provision_admin(session, original)
    headers = admin_login(client, original)
    other_headers = admin_login(client, original)
    original_id = client.get("/api/v1/auth/me", headers=headers).json()["id"]
    with database.connect() as connection:
        original_hash = connection.scalar(text("SELECT password_hash FROM accounts"))
    with Session(database) as session, session.begin():
        provision_admin(session, bootstrap_settings("changed-test-password"))
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.get("/api/v1/auth/me", headers=other_headers).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "operator@example.com", "password": "operator-test-password"},
        ).status_code
        == 401
    )
    new_headers = admin_login(client, bootstrap_settings("changed-test-password"))
    account = client.get("/api/v1/auth/me", headers=new_headers).json()
    assert (account["id"], account["role"]) == (original_id, "ADMIN")
    with database.connect() as connection:
        assert connection.scalar(text("SELECT password_hash FROM accounts")) != original_hash
        assert connection.scalar(text("SELECT count(*) FROM accounts")) == 1
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM lifecycle_events WHERE action = 'ADMIN_PASSWORD_ROTATED'"
                )
            )
            == 1
        )


def test_database_rejects_a_second_admin_independently_of_bootstrap(database):
    with Session(database) as session, session.begin():
        provision_admin(session, bootstrap_settings())
    with pytest.raises(IntegrityError), Session(database) as session, session.begin():
        session.add(
            AccountRecord(
                id=uuid4(),
                email="other-admin@example.com",
                role="ADMIN",
                password_hash="unused-test-fixture-hash",
            )
        )
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM accounts")) == 1
        assert connection.scalar(text("SELECT count(*) FROM lifecycle_events")) == 1


def test_bootstrap_never_reopens_closed_admin_even_with_correct_password(client, database):
    settings = bootstrap_settings()
    with Session(database) as session, session.begin():
        provision_admin(session, settings)
    headers = admin_login(client, settings)
    assert client.delete("/api/v1/auth/me", headers=headers).status_code == 204
    with database.connect() as connection:
        original = connection.execute(
            text("SELECT id, password_hash, deleted_at FROM accounts")
        ).one()
        event_count = connection.scalar(text("SELECT count(*) FROM lifecycle_events"))
    with (
        pytest.raises(ValueError, match="closed account"),
        Session(database) as session,
        session.begin(),
    ):
        provision_admin(session, settings)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "operator@example.com", "password": "operator-test-password"},
        ).status_code
        == 401
    )
    with database.connect() as connection:
        assert (
            connection.execute(text("SELECT id, password_hash, deleted_at FROM accounts")).one()
            == original
        )
        assert connection.scalar(text("SELECT count(*) FROM lifecycle_events")) == event_count


def test_promotion_preserves_existing_user_identity_password_and_organization(client, database):
    settings = bootstrap_settings()
    body = {"email": "operator@example.com", "password": "operator-test-password"}
    created = client.post("/api/v1/auth/register", json=body)
    assert created.status_code == 201
    headers = admin_login(client, settings)
    organization = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "Promotion fixture", "type": "NGO", "location": "Centro"},
    )
    assert organization.status_code == 201
    with database.connect() as connection:
        original_hash = connection.scalar(text("SELECT password_hash FROM accounts"))
    with Session(database) as session, session.begin():
        provision_admin(session, settings)
    assert client.get("/api/v1/auth/me", headers=headers).json() == {
        **created.json(),
        "role": "ADMIN",
    }
    assert (
        client.get(organization.headers["Location"], headers=headers).json() == organization.json()
    )
    with database.connect() as connection:
        assert connection.scalar(text("SELECT password_hash FROM accounts")) == original_hash
        assert connection.scalar(text("SELECT count(*) FROM accounts")) == 1
        event = connection.execute(
            text("SELECT account_id, action FROM lifecycle_events WHERE action = 'ADMIN_GRANTED'")
        ).one()
        assert str(event.account_id) == created.json()["id"]


@pytest.mark.parametrize("existing_user", [False, True])
def test_failed_admin_audit_rolls_back_account_creation_or_promotion(
    client, database, existing_user
):
    settings = bootstrap_settings()
    if existing_user:
        assert (
            client.post(
                "/api/v1/auth/register",
                json={"email": "operator@example.com", "password": "operator-test-password"},
            ).status_code
            == 201
        )
    with database.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE lifecycle_events ADD CONSTRAINT test_admin_audit "
                "CHECK (action <> 'ADMIN_GRANTED')"
            )
        )
    try:
        with pytest.raises(IntegrityError), Session(database) as session, session.begin():
            provision_admin(session, settings)
        with database.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM accounts")) == int(existing_user)
            assert (
                connection.scalar(text("SELECT count(*) FROM accounts WHERE role = 'ADMIN'")) == 0
            )
            assert connection.scalar(text("SELECT count(*) FROM lifecycle_events")) == 0
        if existing_user:
            assert (
                client.get("/api/v1/auth/me", headers=admin_login(client, settings)).json()["role"]
                == "USER"
            )
    finally:
        with database.begin() as connection:
            connection.execute(
                text("ALTER TABLE lifecycle_events DROP CONSTRAINT test_admin_audit")
            )


@pytest.mark.parametrize("bootstrapped", [False, True])
@pytest.mark.parametrize("password", ["operator-test-password", "different-signup-password"])
@pytest.mark.parametrize("email", ["operator@example.com", "OPERATOR@EXAMPLE.COM"])
def test_signup_cannot_claim_reserved_admin_email(client, database, bootstrapped, password, email):
    settings = bootstrap_settings()
    client.app.state.settings.admin_email = settings.admin_email
    if bootstrapped:
        with Session(database) as session, session.begin():
            provision_admin(session, settings)
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_unavailable"
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM accounts")) == int(bootstrapped)
    # A rejected signup must leave bootstrap and normal admin login usable.
    with Session(database) as session, session.begin():
        provision_admin(session, settings)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": str(settings.admin_email), "password": "operator-test-password"},
    )
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "ADMIN"


def test_using_bootstrap_password_with_another_email_never_grants_admin(client):
    settings = bootstrap_settings()
    client.app.state.settings.admin_email = settings.admin_email
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "ordinary@example.com",
            "password": settings.admin_password.get_secret_value(),
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "USER"


def test_configured_admin_email_never_grants_privileges_to_existing_user(client):
    settings = bootstrap_settings()
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"email": "operator@example.com", "password": "operator-test-password"},
        ).status_code
        == 201
    )
    headers = admin_login(client, settings)
    client.app.state.settings.admin_email = settings.admin_email
    assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "USER"
    assert (
        client.get(
            "/api/v1/organizations/00000000-0000-0000-0000-000000000000/verification",
            headers=headers,
        ).status_code
        == 403
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
    assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "ADMIN"


@pytest.mark.parametrize("failure_action", ["ADMIN_RETIRED", "ADMIN_GRANTED"])
def test_replacement_audit_failure_keeps_old_admin_and_sessions(client, database, failure_action):
    original = bootstrap_settings()
    with Session(database) as session, session.begin():
        provision_admin(session, original)
    headers = admin_login(client, original)
    original_account = client.get("/api/v1/auth/me", headers=headers).json()
    with database.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE lifecycle_events ADD CONSTRAINT test_replacement_audit "
                f"CHECK (action <> '{failure_action}') NOT VALID"
            )
        )
    try:
        with pytest.raises(IntegrityError), Session(database) as session, session.begin():
            provision_admin(session, bootstrap_settings(email="replacement@example.com"))
        assert client.get("/api/v1/auth/me", headers=headers).json() == original_account
        assert admin_login(client, original)
        with database.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM accounts")) == 1
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM accounts WHERE role = 'ADMIN' AND deleted_at IS NULL"
                    )
                )
                == 1
            )
            assert connection.scalar(text("SELECT count(*) FROM lifecycle_events")) == 1
    finally:
        with database.begin() as connection:
            connection.execute(
                text("ALTER TABLE lifecycle_events DROP CONSTRAINT test_replacement_audit")
            )


def test_password_rotation_audit_failure_preserves_old_credentials_and_sessions(client, database):
    original = bootstrap_settings()
    with Session(database) as session, session.begin():
        provision_admin(session, original)
    headers = admin_login(client, original)
    with database.begin() as connection:
        original_hash = connection.scalar(text("SELECT password_hash FROM accounts"))
        connection.execute(
            text(
                "ALTER TABLE lifecycle_events ADD CONSTRAINT test_password_audit "
                "CHECK (action <> 'ADMIN_PASSWORD_ROTATED')"
            )
        )
    try:
        with pytest.raises(IntegrityError), Session(database) as session, session.begin():
            provision_admin(session, bootstrap_settings("rotated-test-password"))
        assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "ADMIN"
        assert admin_login(client, original)
        with database.connect() as connection:
            assert connection.scalar(text("SELECT password_hash FROM accounts")) == original_hash
            assert connection.scalar(text("SELECT count(*) FROM lifecycle_events")) == 1
    finally:
        with database.begin() as connection:
            connection.execute(
                text("ALTER TABLE lifecycle_events DROP CONSTRAINT test_password_audit")
            )


@pytest.mark.parametrize("closed_target", [False, True])
def test_unavailable_replacement_target_does_not_retire_current_admin(
    client, database, closed_target
):
    original = bootstrap_settings()
    with Session(database) as session, session.begin():
        provision_admin(session, original)
    headers = admin_login(client, original)
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"email": "replacement@example.com", "password": "existing-user-password"},
        ).status_code
        == 201
    )
    if closed_target:
        with database.begin() as connection:
            connection.execute(
                text(
                    "UPDATE accounts SET deleted_at = now() WHERE email = 'replacement@example.com'"
                )
            )
    with pytest.raises(ValueError), Session(database) as session, session.begin():
        provision_admin(session, bootstrap_settings(email="replacement@example.com"))
    assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "ADMIN"
    with database.connect() as connection:
        assert (
            connection.scalar(text("SELECT email FROM accounts WHERE role = 'ADMIN'"))
            == "operator@example.com"
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM lifecycle_events WHERE action = 'ADMIN_RETIRED'")
            )
            == 0
        )


@pytest.mark.parametrize("same_email", [False, True])
@pytest.mark.parametrize("existing_admin", [False, True])
def test_concurrent_bootstrap_leaves_only_one_configured_admin(
    client, database, same_email, existing_admin
):
    original_headers = None
    if existing_admin:
        with Session(database) as session, session.begin():
            provision_admin(session, bootstrap_settings(email="previous@example.com"))
        original_headers = admin_login(client, bootstrap_settings(email="previous@example.com"))
    first = bootstrap_settings("first-test-password", email="first@example.com")
    second = bootstrap_settings(
        "second-test-password", email="first@example.com" if same_email else "second@example.com"
    )
    barrier = Barrier(2)

    def bootstrap(settings):
        with Session(database) as session, session.begin():
            barrier.wait(timeout=10)
            provision_admin(session, settings)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(bootstrap, settings) for settings in (first, second)]
        for future in futures:
            future.result(timeout=20)
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM accounts WHERE role = 'ADMIN'")) == 1
        assert (
            connection.scalar(
                text("SELECT count(*) FROM accounts WHERE role = 'ADMIN' AND deleted_at IS NULL")
            )
            == 1
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM accounts WHERE role = 'USER' AND deleted_at IS NULL")
            )
            == 0
        )
    logins = [
        client.post(
            "/api/v1/auth/login",
            json={
                "email": str(settings.admin_email),
                "password": settings.admin_password.get_secret_value(),
            },
        ).status_code
        for settings in (first, second)
    ]
    assert sorted(logins) == [200, 401]
    if original_headers:
        assert client.get("/api/v1/auth/me", headers=original_headers).status_code == 401


def test_retirement_invalidates_pending_recovery_tokens(client, database):
    original = bootstrap_settings()
    digest = sha256(b"synthetic-recovery-token").hexdigest()
    with Session(database) as session, session.begin():
        provision_admin(session, original)
        account_id = session.scalar(select(AccountRecord.id))
        session.add(
            RecoveryRecord(
                token_hash=digest,
                account_id=account_id,
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
    with Session(database) as session, session.begin():
        provision_admin(session, bootstrap_settings(email="replacement@example.com"))
    with pytest.raises(InvalidInput), Session(database) as session, session.begin():
        SqlAlchemyAccountRepository(session).restore_account(digest)
    with Session(database) as session:
        assert session.get(RecoveryRecord, digest).used_at is not None
        assert session.get(AccountRecord, account_id).deleted_at is not None
        assert session.scalar(text("SELECT count(*) FROM accounts WHERE role = 'ADMIN'")) == 1


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
