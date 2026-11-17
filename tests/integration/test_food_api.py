from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from threading import Barrier, Event
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


def sign_in(client, email="food-owner@example.com"):
    credentials = {"email": email, "password": "test-password-at-least-12"}
    assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
    response = client.post("/api/v1/auth/login", json=credentials)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def organization(client, headers, type="NGO"):
    response = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "Fictional donor", "type": type, "location": "Porto Alegre"},
    )
    assert response.status_code == 201
    return response.json()


def food_payload():
    return {
        "name": " Rice ",
        "category": " Grains ",
        "quantity_kg": "12.125",
        "expiration_date": (
            datetime.now(ZoneInfo("America/Sao_Paulo")).date() + timedelta(days=7)
        ).isoformat(),
    }


@pytest.mark.parametrize("type", ["SUPERMARKET", "NGO", "COMMUNITY_KITCHEN"])
def test_food_crud_persists_for_all_organization_types(client, database, type):
    headers = sign_in(client)
    donor = organization(client, headers, type)
    response = client.post("/api/v1/foods", headers=headers, json=food_payload())
    assert response.status_code == 201, response.text
    food = response.json()
    assert food["name"] == "Rice"
    assert food["category"] == "Grains"
    assert food["donor_organization_id"] == donor["id"]
    assert Decimal(food["quantity_kg"]) == Decimal("12.125")
    other = sign_in(client, "reader@example.com")
    assert client.get(response.headers["Location"], headers=other).json() == food
    assert client.get("/api/v1/foods", headers=other).json() == [food]
    with database.connect() as connection:
        assert connection.scalar(text("SELECT quantity_kg FROM foods")) == Decimal("12.125")
    deleted = client.delete(f"/api/v1/organizations/{donor['id']}", headers=headers)
    assert deleted.status_code == 409
    assert deleted.json()["error"]["code"] == "organization_in_use"
    assert client.get(response.headers["Location"], headers=headers).json() == food
    path = response.headers["Location"]
    updated = client.put(
        path,
        headers=headers,
        json={**food_payload(), "name": " Beans ", "category": " Legumes ", "quantity_kg": "3.750"},
    )
    assert updated.status_code == 200, updated.text
    assert (updated.json()["id"], updated.json()["donor_organization_id"]) == (
        food["id"],
        donor["id"],
    )
    assert (updated.json()["name"], updated.json()["category"], updated.json()["quantity_kg"]) == (
        "Beans",
        "Legumes",
        "3.750",
    )
    assert client.get(path, headers=other).json() == updated.json()
    assert client.get("/api/v1/foods", headers=headers).json() == [updated.json()]
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path, headers=headers).status_code == 404
    assert client.get("/api/v1/foods", headers=headers).json() == []
    assert client.delete(f"/api/v1/organizations/{donor['id']}", headers=headers).status_code == 204


def test_registration_requires_authentication_and_own_organization(client):
    headers = sign_in(client)
    other = sign_in(client, "other-donor@example.com")
    donor = organization(client, other)
    denied = client.post("/api/v1/foods", headers=headers, json=food_payload())
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "organization_required"
    organization(client, headers)
    spoofed = client.post(
        "/api/v1/foods",
        headers=other,
        json={**food_payload(), "donor_organization_id": str(uuid4())},
    )
    assert spoofed.status_code == 422
    assert client.get("/api/v1/foods", headers=headers).json() == []
    created = client.post("/api/v1/foods", headers=other, json=food_payload())
    assert created.json()["donor_organization_id"] == donor["id"]
    path = created.headers["Location"]
    assert client.put(path, headers=headers, json=food_payload()).status_code == 403
    assert client.delete(path, headers=headers).status_code == 403
    assert client.get(path, headers=other).json() == created.json()
    for method, target, payload in [
        ("POST", "/api/v1/foods", food_payload()),
        ("GET", "/api/v1/foods", None),
        ("GET", created.headers["Location"], None),
        ("PUT", path, food_payload()),
        ("DELETE", path, None),
    ]:
        assert client.request(method, target, json=payload).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"name": "x" * 161},
        {"category": " "},
        {"category": "x" * 81},
        {"quantity_kg": "0"},
        {"quantity_kg": "-1"},
        {"quantity_kg": "0.0001"},
        {"quantity_kg": "1000000000"},
        {"quantity_kg": "NaN"},
        {"quantity_kg": "Infinity"},
        {"expiration_date": "not-a-date"},
        {"expiration_date": "2000-01-01"},
        {"name": None},
        {"category": None},
        {"quantity_kg": None},
        {"expiration_date": None},
        {"donor_organization_id": str(uuid4())},
        {"id": str(uuid4())},
    ],
)
def test_invalid_registration_and_update_preserve_data(client, changes):
    headers = sign_in(client)
    organization(client, headers)
    response = client.post("/api/v1/foods", headers=headers, json={**food_payload(), **changes})
    assert response.status_code == 422, response.text
    assert client.get("/api/v1/foods", headers=headers).json() == []
    created = client.post("/api/v1/foods", headers=headers, json=food_payload())
    path = created.headers["Location"]
    response = client.put(path, headers=headers, json={**food_payload(), **changes})
    assert response.status_code == 422, response.text
    assert client.get(path, headers=headers).json() == created.json()


def test_required_fields_and_pagination(client):
    headers = sign_in(client)
    organization(client, headers)
    for field in food_payload():
        payload = food_payload()
        del payload[field]
        assert client.post("/api/v1/foods", headers=headers, json=payload).status_code == 422
    for name in ["Zulu", "Alpha", "Alpha"]:
        response = client.post(
            "/api/v1/foods", headers=headers, json={**food_payload(), "name": name}
        )
        assert response.status_code == 201
    pages = [
        client.get(f"/api/v1/foods?limit=1&offset={i}", headers=headers).json()[0] for i in range(3)
    ]
    assert [food["name"] for food in pages] == ["Alpha", "Alpha", "Zulu"]
    assert len({food["id"] for food in pages}) == 3
    assert pages[0]["id"] < pages[1]["id"]
    assert client.get("/api/v1/foods?offset=3", headers=headers).json() == []
    for query in ["limit=0", "limit=101", "offset=-1"]:
        assert client.get(f"/api/v1/foods?{query}", headers=headers).status_code == 422
    assert client.get(f"/api/v1/foods/{uuid4()}", headers=headers).status_code == 404
    assert (
        client.put(f"/api/v1/foods/{uuid4()}", headers=headers, json=food_payload()).status_code
        == 404
    )
    assert client.delete(f"/api/v1/foods/{uuid4()}", headers=headers).status_code == 404
    for field in food_payload():
        payload = food_payload()
        del payload[field]
        assert (
            client.put(response.headers["Location"], headers=headers, json=payload).status_code
            == 422
        )
    assert client.get(response.headers["Location"], headers=headers).json() == response.json()


def test_quantity_boundaries_and_expiring_today(client):
    headers = sign_in(client)
    organization(client, headers)
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    for quantity in ["0.001", "999999999.999", "1", 0.1]:
        response = client.post(
            "/api/v1/foods",
            headers=headers,
            json={**food_payload(), "quantity_kg": quantity, "expiration_date": today},
        )
        assert response.status_code == 201, response.text
        assert client.get(response.headers["Location"], headers=headers).json() == response.json()


def test_expired_record_remains_readable_for_history(client, database):
    headers = sign_in(client)
    organization(client, headers)
    created = client.post("/api/v1/foods", headers=headers, json=food_payload())
    with database.begin() as connection:
        connection.execute(text("UPDATE foods SET expiration_date = '2000-01-01'"))
    assert client.get(created.headers["Location"], headers=headers).json()["expiration_date"] == (
        "2000-01-01"
    )
    assert len(client.get("/api/v1/foods", headers=headers).json()) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"category": " "},
        {"quantity_kg": "0"},
        {"quantity_kg": "NaN"},
        {"donor_organization_id": str(uuid4())},
    ],
)
def test_database_constraints_reject_invalid_food(database, client, changes):
    headers = sign_in(client)
    donor = organization(client, headers)
    values = {
        "id": uuid4(),
        "donor_organization_id": donor["id"],
        "name": "Rice",
        "category": "Grains",
        "quantity_kg": "1",
        **changes,
    }
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO foods (id, donor_organization_id, name, category, quantity_kg, "
                "expiration_date) VALUES (:id, :donor_organization_id, :name, :category, "
                ":quantity_kg, CURRENT_DATE)"
            ),
            values,
        )
    assert client.get("/api/v1/foods", headers=headers).json() == []


def test_database_failure_rolls_back_food_registration(client, database):
    headers = sign_in(client)
    organization(client, headers)
    with database.begin() as connection:
        connection.execute(
            text("ALTER TABLE foods ADD CONSTRAINT test_food_name CHECK (name <> 'Rice')")
        )
    try:
        response = client.post("/api/v1/foods", headers=headers, json=food_payload())
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "data_conflict"
        assert client.get("/api/v1/foods", headers=headers).json() == []
    finally:
        with database.begin() as connection:
            connection.execute(text("ALTER TABLE foods DROP CONSTRAINT test_food_name"))


def test_concurrent_registration_and_organization_deletion_preserve_integrity(client):
    headers = sign_in(client)
    donor = organization(client, headers)
    barrier = Barrier(2)

    def register():
        barrier.wait(timeout=10)
        return client.post("/api/v1/foods", headers=headers, json=food_payload()).status_code

    def delete():
        barrier.wait(timeout=10)
        return client.delete(f"/api/v1/organizations/{donor['id']}", headers=headers).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        registration, deletion = executor.submit(register), executor.submit(delete)
        outcomes = registration.result(), deletion.result()
    assert outcomes in [(201, 409), (403, 204)]
    records = client.get("/api/v1/foods", headers=headers).json()
    assert len(records) == (1 if outcomes[0] == 201 else 0)


@pytest.fixture
def listing(client):
    headers = sign_in(client)
    donor = organization(client, headers)
    created = client.post("/api/v1/foods", headers=headers, json=food_payload())
    assert created.status_code == 201
    return headers, donor, created.json(), created.headers["Location"]


@pytest.fixture
def recipient(client):
    headers = sign_in(client, "recipient@example.com")
    return headers, organization(client, headers)


def seed_request(connection, food_id, recipient_id, status, quantity="1"):
    # E03 endpoints are pending; these persisted fixtures exercise E02 history constraints.
    request_id = uuid4()
    connection.execute(
        text(
            "INSERT INTO food_requests "
            "(id, food_id, recipient_organization_id, quantity_kg, status) "
            "VALUES (:id, :food_id, :recipient_id, :quantity, :status)"
        ),
        {
            "id": request_id,
            "food_id": food_id,
            "recipient_id": recipient_id,
            "quantity": quantity,
            "status": status,
        },
    )
    return request_id


@pytest.mark.parametrize("status", ["PENDING", "APPROVED", "REJECTED"])
def test_food_with_any_request_status_cannot_be_deleted(
    client, database, listing, recipient, status
):
    headers, _, food, path = listing
    recipient_headers, recipient_organization = recipient
    with database.begin() as connection:
        request_id = seed_request(connection, food["id"], recipient_organization["id"], status)
    response = client.delete(path, headers=headers)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "food_in_use"
    assert client.get(path, headers=headers).json() == food
    assert (
        client.delete(
            f"/api/v1/organizations/{recipient_organization['id']}", headers=recipient_headers
        ).status_code
        == 409
    )
    with database.connect() as connection:
        record = connection.execute(
            text("SELECT status, quantity_kg, created_at FROM food_requests WHERE id = :id"),
            {"id": request_id},
        ).one()
        assert (record.status, record.quantity_kg) == (status, Decimal("1"))
        assert record.created_at.utcoffset() is not None


def test_update_uses_sum_of_only_this_foods_approved_requests(client, database, listing, recipient):
    headers, _, food, path = listing
    _, recipient_organization = recipient
    other = client.post("/api/v1/foods", headers=headers, json=food_payload()).json()
    with database.begin() as connection:
        for status, quantity in [
            ("APPROVED", "6.250"),
            ("APPROVED", "3.750"),
            ("PENDING", "12"),
            ("REJECTED", "12"),
        ]:
            seed_request(connection, food["id"], recipient_organization["id"], status, quantity)
        seed_request(connection, other["id"], recipient_organization["id"], "APPROVED", "8")
    rejected = client.put(
        path,
        headers=headers,
        json={**food_payload(), "quantity_kg": "9.999", "name": "Rejected edit"},
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["error"]["code"] == "food_quantity_below_approved"
    assert client.get(path, headers=headers).json() == food
    for quantity in ["10", "10.001"]:
        response = client.put(
            path, headers=headers, json={**food_payload(), "quantity_kg": quantity}
        )
        assert response.status_code == 200, response.text
        assert Decimal(response.json()["quantity_kg"]) == Decimal(quantity)
        assert client.get(path, headers=headers).json() == response.json()
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM food_requests")) == 5


@pytest.mark.parametrize("status", ["PENDING", "REJECTED"])
def test_unapproved_requests_do_not_reserve_food_quantity(
    client, database, listing, recipient, status
):
    headers, _, food, path = listing
    _, recipient_organization = recipient
    with database.begin() as connection:
        seed_request(connection, food["id"], recipient_organization["id"], status, "12")
    response = client.put(path, headers=headers, json={**food_payload(), "quantity_kg": "0.001"})
    assert response.status_code == 200, response.text
    assert response.json()["quantity_kg"] == "0.001"
    assert client.delete(path, headers=headers).status_code == 409


def test_food_filter_applies_before_pagination(client, listing, recipient):
    headers, donor, _, _ = listing
    other_headers, other_donor = recipient
    for name in ["Alpha", "Zulu"]:
        assert (
            client.post(
                "/api/v1/foods", headers=headers, json={**food_payload(), "name": name}
            ).status_code
            == 201
        )
    assert (
        client.post(
            "/api/v1/foods", headers=other_headers, json={**food_payload(), "name": "Aardvark"}
        ).status_code
        == 201
    )
    path = f"/api/v1/foods?donor_organization_id={donor['id']}"
    pages = [
        client.get(f"{path}&limit=1&offset={offset}", headers=other_headers).json()
        for offset in range(3)
    ]
    assert [page[0]["name"] for page in pages] == ["Alpha", "Rice", "Zulu"]
    assert all(page[0]["donor_organization_id"] == donor["id"] for page in pages)
    other_food = client.get(
        f"/api/v1/foods?donor_organization_id={other_donor['id']}", headers=headers
    ).json()
    assert [food["name"] for food in other_food] == ["Aardvark"]
    assert client.get(f"{path}&offset=3", headers=headers).json() == []
    assert (
        client.get(f"/api/v1/foods?donor_organization_id={uuid4()}", headers=headers).json() == []
    )
    assert (
        client.get("/api/v1/foods?donor_organization_id=invalid", headers=headers).status_code
        == 422
    )


def test_expired_unused_food_can_be_deleted(client, database, listing):
    headers, _, _, path = listing
    with database.begin() as connection:
        connection.execute(text("UPDATE foods SET expiration_date = '2000-01-01'"))
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path, headers=headers).status_code == 404


def test_food_update_failure_rolls_back_all_changes(client, database, listing):
    headers, _, food, path = listing
    with database.begin() as connection:
        connection.execute(
            text("ALTER TABLE foods ADD CONSTRAINT test_food_update_name CHECK (name <> 'Blocked')")
        )
    try:
        response = client.put(
            path,
            headers=headers,
            json={**food_payload(), "name": "Blocked", "quantity_kg": "1"},
        )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "data_conflict"
        assert client.get(path, headers=headers).json() == food
    finally:
        with database.begin() as connection:
            connection.execute(text("ALTER TABLE foods DROP CONSTRAINT test_food_update_name"))


def test_edit_waits_for_locked_food_and_reads_committed_approved_total(
    client, database, listing, recipient, monkeypatch
):
    from app.infrastructure.repository import SqlAlchemyRepository

    headers, _, food, path = listing
    _, recipient_organization = recipient
    attempted = Event()
    original_get = SqlAlchemyRepository.get_food

    def observed_get(repository, food_id, *, lock=False):
        if lock:
            attempted.set()
        return original_get(repository, food_id, lock=lock)

    monkeypatch.setattr(SqlAlchemyRepository, "get_food", observed_get)
    with ThreadPoolExecutor(max_workers=1) as executor:
        # Simulate the lock contract required of the future E03 approval transaction.
        with database.begin() as connection:
            connection.execute(
                text("SELECT id FROM foods WHERE id = :id FOR UPDATE"), {"id": food["id"]}
            )
            edit = executor.submit(
                client.put,
                path,
                headers=headers,
                json={**food_payload(), "quantity_kg": "5"},
            )
            assert attempted.wait(timeout=10)
            seed_request(connection, food["id"], recipient_organization["id"], "APPROVED", "8")
        response = edit.result(timeout=10)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "food_quantity_below_approved"
    assert client.get(path, headers=headers).json() == food


def test_deletion_waits_for_in_flight_request_and_preserves_history(
    client, database, listing, recipient, monkeypatch
):
    from app.infrastructure.repository import SqlAlchemyRepository

    headers, _, food, path = listing
    _, recipient_organization = recipient
    attempted = Event()
    original_get = SqlAlchemyRepository.get_food

    def observed_get(repository, food_id, *, lock=False):
        if lock:
            attempted.set()
        return original_get(repository, food_id, lock=lock)

    monkeypatch.setattr(SqlAlchemyRepository, "get_food", observed_get)
    with ThreadPoolExecutor(max_workers=1) as executor:
        with database.begin() as connection:
            connection.execute(
                text("SELECT id FROM foods WHERE id = :id FOR UPDATE"), {"id": food["id"]}
            )
            deletion = executor.submit(client.delete, path, headers=headers)
            assert attempted.wait(timeout=10)
            seed_request(connection, food["id"], recipient_organization["id"], "PENDING")
        response = deletion.result(timeout=10)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "food_in_use"
    assert client.get(path, headers=headers).json() == food
