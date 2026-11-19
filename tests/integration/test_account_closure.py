import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


def owner(client):
    credentials = {"email": "closure@example.com", "password": "password8"}
    assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
    token = client.post("/api/v1/auth/login", json=credentials).json()["access_token"]
    return credentials, {"Authorization": f"Bearer {token}"}


def org(client, headers):
    response = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "Archive fixture", "type": "NGO", "location": "Centro"},
    )
    assert response.status_code == 201
    # Verified donor fixture; review permissions and transitions have dedicated API tests.
    from sqlalchemy import text

    with client.app.state.engine.begin() as connection:
        connection.execute(
            text("UPDATE organizations SET verification_status = 'VERIFIED' WHERE id = :id"),
            {"id": response.json()["id"]},
        )
    return response.headers["Location"]


def test_org_archive_preserves_row_and_allows_replacement(client, database):
    _, headers = owner(client)
    path = org(client, headers)
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path, headers=headers).status_code == 404
    assert client.get("/api/v1/organizations", headers=headers).json() == []
    assert client.delete(path, headers=headers).status_code == 404
    with database.connect() as connection:
        archived = connection.scalar(text("SELECT deleted_at FROM organizations"))
        assert archived is not None and archived.utcoffset() is not None
    assert org(client, headers) != path
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM organizations")) == 2


@pytest.mark.parametrize("with_org", [False, True])
def test_account_closure_revokes_login_and_existing_tokens(client, database, with_org):
    credentials, headers = owner(client)
    if with_org:
        org(client, headers)
    assert client.delete("/api/v1/auth/me", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.get("/api/v1/foods", headers=headers).status_code == 401
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 401
    assert client.post("/api/v1/auth/register", json=credentials).status_code == 409
    with database.connect() as connection:
        assert connection.scalar(text("SELECT deleted_at FROM accounts")) is not None
        if with_org:
            assert connection.scalar(text("SELECT deleted_at FROM organizations")) is not None


def test_closure_conflict_preserves_active_account_org_and_food(client, database):
    credentials, headers = owner(client)
    path = org(client, headers)
    food = client.post(
        "/api/v1/foods",
        headers=headers,
        json={
            "name": "Rice",
            "category": "Grains",
            "quantity_kg": "1",
            "expiration_date": "9999-12-31",
        },
    )
    assert food.status_code == 201
    assert client.delete("/api/v1/auth/me", headers=headers).status_code == 409
    assert client.get(path, headers=headers).status_code == 200
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 200
    with database.connect() as connection:
        assert connection.scalar(text("SELECT deleted_at FROM accounts")) is None
        assert connection.scalar(text("SELECT deleted_at FROM organizations")) is None
    assert client.delete(food.headers["Location"], headers=headers).status_code == 204
    assert client.delete("/api/v1/auth/me", headers=headers).status_code == 204


def test_account_closure_requires_authentication(client):
    assert client.delete("/api/v1/auth/me").status_code == 401
