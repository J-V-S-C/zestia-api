from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

pytestmark = [pytest.mark.integration, pytest.mark.e2e]
PASSWORD = "test-password-at-least-12"


def sign_in(client: TestClient, email: str = "owner@example.com") -> dict[str, str]:
    registered = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert registered.status_code == 201, registered.text
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def organization_payload(type: str = "NGO") -> dict[str, str]:
    return {"name": " Fictional organization ", "type": type, "location": " Porto Alegre "}


@pytest.mark.parametrize("type", ["SUPERMARKET", "NGO", "COMMUNITY_KITCHEN"])
def test_crud_persists_for_each_institution_type(client: TestClient, type: str) -> None:
    headers = sign_in(client)
    created = client.post("/api/v1/organizations", headers=headers, json=organization_payload(type))
    assert created.status_code == 201, created.text
    path = created.headers["Location"]
    assert created.json()["name"] == "Fictional organization"
    assert "owner_account_id" not in created.json()
    assert client.get(path, headers=headers).json() == created.json()
    assert client.get("/api/v1/organizations", headers=headers).json() == [created.json()]
    updated = client.put(
        path,
        headers=headers,
        json={**organization_payload(type), "name": "Updated", "location": "Floresta"},
    )
    assert updated.status_code == 200, updated.text
    assert client.get(path, headers=headers).json()["location"] == "Floresta"
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path, headers=headers).status_code == 404
    assert client.get("/api/v1/organizations", headers=headers).json() == []
    # Deleting an organization keeps the account and allows registering its replacement.
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert (
        client.post(
            "/api/v1/organizations", headers=headers, json=organization_payload(type)
        ).status_code
        == 201
    )


def test_ownership_and_authentication(client: TestClient) -> None:
    owner = sign_in(client)
    other = sign_in(client, "other@example.com")
    path = client.post("/api/v1/organizations", headers=owner, json=organization_payload()).headers[
        "Location"
    ]
    assert client.get(path, headers=other).status_code == 200
    assert client.put(path, headers=other, json=organization_payload()).status_code == 403
    assert client.delete(path, headers=other).status_code == 403
    for method, target, payload in [
        ("GET", "/api/v1/organizations", None),
        ("POST", "/api/v1/organizations", organization_payload()),
        ("GET", path, None),
        ("PUT", path, organization_payload()),
        ("DELETE", path, None),
    ]:
        assert client.request(method, target, json=payload).status_code == 401
    assert client.get(path, headers=owner).status_code == 200


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"location": " "},
        {"name": "x" * 161},
        {"location": "x" * 241},
        {"type": "donor"},
        {"owner_account_id": str(uuid4())},
    ],
)
def test_invalid_create_and_update_preserve_data(client: TestClient, changes: dict) -> None:
    headers = sign_in(client)
    invalid = {**organization_payload(), **changes}
    assert client.post("/api/v1/organizations", headers=headers, json=invalid).status_code == 422
    created = client.post("/api/v1/organizations", headers=headers, json=organization_payload())
    path = created.headers["Location"]
    assert client.put(path, headers=headers, json=invalid).status_code == 422
    assert client.get(path, headers=headers).json() == created.json()


def test_concurrent_creations_preserve_one_organization_per_account(
    client: TestClient, monkeypatch
) -> None:
    from threading import Barrier

    from app.infrastructure.repository import SqlAlchemyRepository

    headers = sign_in(client)
    barrier = Barrier(2)
    original_save = SqlAlchemyRepository.save_organization

    def simultaneous_save(repository, organization):
        barrier.wait(timeout=10)
        original_save(repository, organization)

    monkeypatch.setattr(SqlAlchemyRepository, "save_organization", simultaneous_save)

    def create(_: int) -> int:
        return client.post(
            "/api/v1/organizations", headers=headers, json=organization_payload()
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(create, [0, 1])) == [201, 409]
    assert len(client.get("/api/v1/organizations", headers=headers).json()) == 1


def test_deletion_with_dependent_records_is_rejected(client: TestClient, database: Engine) -> None:
    headers = sign_in(client)
    created = client.post("/api/v1/organizations", headers=headers, json=organization_payload())
    # Exercise RN-02 with a real referencing record, without implementing E02/E03 models.
    with database.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE e01_test_reference "
                "(organization_id uuid REFERENCES organizations(id) ON DELETE RESTRICT)"
            )
        )
        connection.execute(
            text("INSERT INTO e01_test_reference VALUES (:id)"), {"id": created.json()["id"]}
        )
    try:
        response = client.delete(created.headers["Location"], headers=headers)
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "organization_in_use"
        assert client.get(created.headers["Location"], headers=headers).status_code == 200
    finally:
        with database.begin() as connection:
            connection.execute(text("DROP TABLE e01_test_reference"))


def test_duplicate_email_and_login_errors(client: TestClient, database: Engine) -> None:
    sign_in(client)
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": "OWNER@example.com", "password": PASSWORD}
        ).status_code
        == 409
    )
    for email in ["owner@example.com", "unknown@example.com"]:
        response = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"
    with database.connect() as connection:
        password_hash = connection.scalar(text("SELECT password_hash FROM accounts"))
        assert password_hash.startswith("$argon2id$")
        assert PASSWORD not in password_hash


@pytest.mark.parametrize("kind", ["expired", "wrong_signature", "malformed", "missing_expiration"])
def test_invalid_tokens(client: TestClient, kind: str) -> None:
    secret = "a-test-secret-at-least-32-characters-long"
    claims = {
        "sub": str(uuid4()),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "iss": "realimenta",
        "aud": "realimenta-api",
    }
    if kind == "expired":
        claims["exp"] = datetime.now(UTC) - timedelta(minutes=5)
    elif kind == "wrong_signature":
        secret = "a-different-secret-at-least-32-characters-long"
    elif kind == "missing_expiration":
        claims.pop("exp")
    token = "invalid" if kind == "malformed" else jwt.encode(claims, secret, algorithm="HS256")
    assert (
        client.get(
            "/api/v1/organizations", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 401
    )


def test_pagination_and_unknown_resources(client: TestClient) -> None:
    headers = sign_in(client)
    missing = f"/api/v1/organizations/{uuid4()}"
    assert client.get(missing, headers=headers).status_code == 404
    assert client.put(missing, headers=headers, json=organization_payload()).status_code == 404
    assert client.delete(missing, headers=headers).status_code == 404
    for query in ["limit=0", "limit=101", "offset=-1"]:
        assert client.get(f"/api/v1/organizations?{query}", headers=headers).status_code == 422
    client.post("/api/v1/organizations", headers=headers, json=organization_payload())
    assert client.get("/api/v1/organizations?offset=1", headers=headers).json() == []
    assert client.get("/health/ready").status_code == 200


def test_validation_does_not_echo_password(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json={"email": "bad", "password": "private"})
    assert response.status_code == 422
    assert "private" not in response.text


def test_token_for_deleted_account_cannot_access_data(client, database):
    headers = sign_in(client)
    with database.begin() as connection:
        connection.execute(text("DELETE FROM accounts"))
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_pagination_has_stable_order_and_does_not_repeat_records(client):
    first = sign_in(client, "first@example.com")
    second = sign_in(client, "second@example.com")
    for headers, name in [(first, "Zulu"), (second, "Alpha")]:
        assert (
            client.post(
                "/api/v1/organizations",
                headers=headers,
                json={**organization_payload(), "name": name},
            ).status_code
            == 201
        )
    page_one = client.get("/api/v1/organizations?limit=1", headers=first).json()
    page_two = client.get("/api/v1/organizations?limit=1&offset=1", headers=first).json()
    assert [page_one[0]["name"], page_two[0]["name"]] == ["Alpha", "Zulu"]
    assert page_one[0]["id"] != page_two[0]["id"]


def test_health_reports_database_failure_without_leaking_credentials():
    from app.config import Settings
    from app.main import create_app

    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://invalid:private-password@127.0.0.1:1/unavailable",
        jwt_secret="test-secret-at-least-32-characters-long",
    )
    with TestClient(create_app(settings)) as unhealthy:
        assert unhealthy.get("/health/live").json() == {"status": "ok"}
        response = unhealthy.get("/health/ready")
        assert response.status_code == 503
        assert "private-password" not in response.text
        assert response.json()["error"]["code"] == "database_unavailable"


def test_cors_allows_configured_frontend_only(client):
    for origin, allowed in [("http://localhost:3000", True), ("https://untrusted.example", False)]:
        response = client.options(
            "/api/v1/organizations",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert (response.headers.get("access-control-allow-origin") == origin) is allowed


def test_concurrent_email_registration_is_atomic(client, monkeypatch, database):
    from threading import Barrier

    barrier = Barrier(2)
    original_hash = client.app.state.hasher.hash

    def simultaneous_hash(password):
        barrier.wait(timeout=10)
        return original_hash(password)

    monkeypatch.setattr(client.app.state.hasher, "hash", simultaneous_hash)

    def register(_):
        return client.post(
            "/api/v1/auth/register", json={"email": "same@example.com", "password": PASSWORD}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(register, [0, 1])) == [201, 409]
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM accounts")) == 1


def test_database_constraint_failure_rolls_back_write_and_returns_safe_conflict(client, database):
    headers = sign_in(client)
    # A database-only restriction exercises a failure after HTTP/domain validation.
    with database.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE organizations ADD CONSTRAINT e01_test_location "
                "CHECK (location <> 'reserved-test-location')"
            )
        )
    try:
        response = client.post(
            "/api/v1/organizations",
            headers=headers,
            json={**organization_payload(), "location": "reserved-test-location"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "data_conflict"
        assert "INSERT" not in response.text
        assert client.get("/api/v1/organizations", headers=headers).json() == []
    finally:
        with database.begin() as connection:
            connection.execute(text("ALTER TABLE organizations DROP CONSTRAINT e01_test_location"))
