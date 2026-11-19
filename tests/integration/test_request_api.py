from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from threading import Barrier, Event
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.application.errors import BusinessError
from app.application.services.requests import FoodRequestService
from app.infrastructure.repository import SqlAlchemyRepository
from tests.integration.test_food_api import food_payload, organization, sign_in

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


@pytest.fixture
def participants(client):
    donor_headers = sign_in(client, "request-donor@example.com")
    donor = organization(client, donor_headers, "SUPERMARKET")
    recipient_headers = sign_in(client, "request-recipient@example.com")
    recipient = organization(client, recipient_headers, "COMMUNITY_KITCHEN")
    response = client.post("/api/v1/foods", headers=donor_headers, json=food_payload())
    assert response.status_code == 201
    return donor_headers, donor, recipient_headers, recipient, response.json()


def create_request(client, headers, food, quantity="6.125"):
    response = client.post(
        "/api/v1/requests",
        headers=headers,
        json={"food_id": food["id"], "quantity_kg": quantity},
    )
    assert response.status_code == 201, response.text
    return response


@pytest.mark.parametrize("type", ["SUPERMARKET", "NGO", "COMMUNITY_KITCHEN"])
def test_request_flow_persists_history_for_all_types(client, database, participants, type):
    donor_headers, donor, headers, recipient, food = participants
    with database.begin() as connection:
        connection.execute(
            text("UPDATE organizations SET type = :type WHERE id = :id"),
            {"type": type, "id": recipient["id"]},
        )
    created = create_request(client, headers, food)
    request = created.json()
    path = created.headers["Location"]
    assert request["status"] == "PENDING"
    assert request["donor_organization_id"] == donor["id"]
    assert request["recipient_organization_id"] == recipient["id"]
    assert request["quantity_kg"] == "6.125"
    assert datetime.fromisoformat(request["created_at"]).utcoffset() is not None
    for actor in [donor_headers, headers]:
        assert client.get(path, headers=actor).json() == request
        assert client.get("/api/v1/requests", headers=actor).json() == [request]
    approved = client.post(f"{path}/approve", headers=donor_headers)
    assert approved.status_code == 200, approved.text
    assert approved.json() == {**request, "status": "APPROVED"}
    assert client.get(path, headers=headers).json() == approved.json()
    with database.connect() as connection:
        record = connection.execute(
            text("SELECT status, quantity_kg FROM food_requests WHERE id = :id"),
            {"id": request["id"]},
        ).one()
        assert (record.status, record.quantity_kg) == ("APPROVED", Decimal("6.125"))
    assert client.get(f"/api/v1/foods/{food['id']}", headers=headers).json() == food
    assert client.delete(f"/api/v1/foods/{food['id']}", headers=donor_headers).status_code == 409
    assert client.delete("/api/v1/auth/me", headers=headers).status_code == 409


def test_pending_does_not_reserve_and_approval_rechecks_balance(client, participants):
    donor, _, recipient, _, food = participants
    first = create_request(client, recipient, food, "10")
    second = create_request(client, recipient, food, "10")
    assert client.post(f"{first.headers['Location']}/approve", headers=donor).status_code == 200
    denied = client.post(f"{second.headers['Location']}/approve", headers=donor)
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "insufficient_food"
    assert client.get(second.headers["Location"], headers=recipient).json()["status"] == "PENDING"
    exhausted = client.post(
        "/api/v1/requests", headers=recipient, json={"food_id": food["id"], "quantity_kg": "2.126"}
    )
    assert exhausted.status_code == 409
    remainder = create_request(client, recipient, food, "2.125")
    assert client.post(f"{remainder.headers['Location']}/approve", headers=donor).status_code == 200
    assert (
        client.post(
            "/api/v1/requests",
            headers=recipient,
            json={"food_id": food["id"], "quantity_kg": "0.001"},
        ).status_code
        == 409
    )
    assert client.post(f"{second.headers['Location']}/reject", headers=donor).status_code == 200


@pytest.mark.parametrize(
    "quantity", ["0", "-1", "0.0001", "1000000000", "NaN", "Infinity", None, "text"]
)
def test_invalid_quantity_has_no_side_effects(client, database, participants, quantity):
    _, _, recipient, _, food = participants
    response = client.post(
        "/api/v1/requests", headers=recipient, json={"food_id": food["id"], "quantity_kg": quantity}
    )
    assert response.status_code == 422, response.text
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM food_requests")) == 0


@pytest.mark.parametrize(
    "field", ["recipient_organization_id", "donor_organization_id", "status", "created_at", "id"]
)
def test_client_cannot_choose_ownership_status_or_identity(client, participants, field):
    _, _, recipient, _, food = participants
    response = client.post(
        "/api/v1/requests",
        headers=recipient,
        json={"food_id": food["id"], "quantity_kg": "1", field: str(uuid4())},
    )
    assert response.status_code == 422


def test_self_expired_missing_food_and_missing_organization(client, database, participants):
    donor, _, recipient, _, food = participants
    payload = {"food_id": food["id"], "quantity_kg": "1"}
    assert client.post("/api/v1/requests", headers=donor, json=payload).status_code == 422
    no_organization = sign_in(client, "no-organization@example.com")
    assert client.get("/api/v1/requests", headers=no_organization).json() == []
    assert client.post("/api/v1/requests", headers=no_organization, json=payload).status_code == 403
    payload["food_id"] = str(uuid4())
    assert client.post("/api/v1/requests", headers=recipient, json=payload).status_code == 404
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    with database.begin() as connection:
        connection.execute(text("UPDATE foods SET expiration_date = :date"), {"date": today})
    pending = create_request(client, recipient, food, "0.001")
    with database.begin() as connection:
        connection.execute(text("UPDATE foods SET expiration_date = '2000-01-01'"))
    assert (
        client.post(
            "/api/v1/requests", headers=recipient, json={"food_id": food["id"], "quantity_kg": "1"}
        ).status_code
        == 422
    )
    assert client.post(f"{pending.headers['Location']}/approve", headers=donor).status_code == 422
    assert client.post(f"{pending.headers['Location']}/reject", headers=donor).status_code == 200


@pytest.mark.parametrize("status", ["PENDING", "REJECTED", "SUSPENDED"])
def test_verification_blocks_participation_and_preserves_history(
    client, database, participants, status
):
    donor, _, recipient, _, food = participants
    pending = create_request(client, recipient, food)
    path = pending.headers["Location"]
    with database.begin() as connection:
        connection.execute(
            text("UPDATE organizations SET verification_status = :status"), {"status": status}
        )
    assert (
        client.post(
            "/api/v1/requests", headers=recipient, json={"food_id": food["id"], "quantity_kg": "1"}
        ).status_code
        == 403
    )
    assert client.post(f"{path}/approve", headers=donor).status_code == 403
    for actor in [donor, recipient]:
        assert client.get(path, headers=actor).json() == pending.json()
        assert client.get("/api/v1/requests", headers=actor).json() == [pending.json()]
    assert client.post(f"{path}/reject", headers=donor).status_code == 200


def test_permissions_and_missing_records(client, participants):
    donor, _, recipient, _, food = participants
    outsider = sign_in(client, "request-outsider@example.com")
    organization(client, outsider)
    created = create_request(client, recipient, food)
    path = created.headers["Location"]
    assert client.get(path, headers=outsider).status_code == 403
    assert client.get("/api/v1/requests", headers=outsider).json() == []
    assert (
        client.get(
            f"/api/v1/requests?donor_organization_id={food['donor_organization_id']}",
            headers=outsider,
        ).json()
        == []
    )
    for actor in [recipient, outsider]:
        for action in ["approve", "reject"]:
            assert client.post(f"{path}/{action}", headers=actor).status_code == 403
    assert client.get(path, headers=donor).json()["status"] == "PENDING"
    missing = f"/api/v1/requests/{uuid4()}"
    assert client.get(missing, headers=donor).status_code == 404
    for action in ["approve", "reject"]:
        assert client.post(f"{missing}/{action}", headers=donor).status_code == 404


@pytest.mark.parametrize("first_action", ["approve", "reject"])
def test_terminal_status_cannot_be_processed_again(client, participants, first_action):
    donor, _, recipient, _, food = participants
    created = create_request(client, recipient, food)
    path = created.headers["Location"]
    processed = client.post(f"{path}/{first_action}", headers=donor)
    assert processed.status_code == 200
    for action in ["approve", "reject"]:
        response = client.post(f"{path}/{action}", headers=donor)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "request_already_processed"
    assert client.get(path, headers=recipient).json() == processed.json()


def test_history_filters_apply_before_pagination_and_include_both_directions(client, participants):
    donor_headers, donor, headers, recipient, food = participants
    first = create_request(client, headers, food)
    second = create_request(client, headers, food, "1")
    rejected = client.post(f"{first.headers['Location']}/reject", headers=donor_headers).json()
    reverse_food = client.post("/api/v1/foods", headers=headers, json=food_payload()).json()
    reverse = create_request(client, donor_headers, reverse_food)
    path = "/api/v1/requests"
    assert client.get(path, headers=headers).json() == [rejected, second.json(), reverse.json()]
    assert client.get(f"{path}?status=PENDING&limit=1&offset=1", headers=headers).json() == [
        reverse.json()
    ]
    assert client.get(
        f"{path}?donor_organization_id={donor['id']}&recipient_organization_id={recipient['id']}",
        headers=headers,
    ).json() == [rejected, second.json()]
    assert client.get(
        f"{path}?recipient_organization_id={donor['id']}", headers=headers
    ).json() == [reverse.json()]
    assert client.get(f"{path}?donor_organization_id={uuid4()}", headers=headers).json() == []
    assert client.get(f"{path}?offset=3", headers=headers).json() == []


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "offset=-1",
        "status=DELIVERED",
        "donor_organization_id=invalid",
        "recipient_organization_id=invalid",
    ],
)
def test_invalid_history_queries_rejected(client, participants, query):
    headers, *_ = participants
    assert client.get(f"/api/v1/requests?{query}", headers=headers).status_code == 422


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("POST", "/api/v1/requests", {"food_id": str(uuid4()), "quantity_kg": "1"}),
        ("GET", "/api/v1/requests", None),
        ("GET", f"/api/v1/requests/{uuid4()}", None),
        ("POST", f"/api/v1/requests/{uuid4()}/approve", None),
        ("POST", f"/api/v1/requests/{uuid4()}/reject", None),
    ],
)
def test_every_request_endpoint_requires_authentication(client, method, path, payload):
    assert client.request(method, path, json=payload).status_code == 401


def test_database_failures_roll_back_creation_and_processing(client, database, participants):
    donor, _, recipient, _, food = participants
    with database.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE food_requests ADD CONSTRAINT test_request_quantity "
                "CHECK (quantity_kg <> 1)"
            )
        )
    try:
        response = client.post(
            "/api/v1/requests", headers=recipient, json={"food_id": food["id"], "quantity_kg": "1"}
        )
        assert response.status_code == 409
        assert client.get("/api/v1/requests", headers=recipient).json() == []
    finally:
        with database.begin() as connection:
            connection.execute(
                text("ALTER TABLE food_requests DROP CONSTRAINT test_request_quantity")
            )
    created = create_request(client, recipient, food)
    with database.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE food_requests ADD CONSTRAINT test_request_approval "
                "CHECK (status <> 'APPROVED')"
            )
        )
    try:
        assert (
            client.post(f"{created.headers['Location']}/approve", headers=donor).status_code == 409
        )
        assert client.get(created.headers["Location"], headers=recipient).json() == created.json()
    finally:
        with database.begin() as connection:
            connection.execute(
                text("ALTER TABLE food_requests DROP CONSTRAINT test_request_approval")
            )


@pytest.mark.parametrize("same_request", [False, True])
def test_concurrent_approvals_in_independent_transactions_preserve_limits(
    client, database, participants, same_request
):
    donor_headers, _, recipient, _, food = participants
    first = create_request(client, recipient, food, "10").json()
    second = first if same_request else create_request(client, recipient, food, "10").json()
    account_id = UUID(client.get("/api/v1/auth/me", headers=donor_headers).json()["id"])
    barrier = Barrier(2)

    def approve(request_id):
        # Bypass authentication's per-account lock to prove the food lock itself works.
        try:
            with Session(database) as session, session.begin():
                repository = SqlAlchemyRepository(session)
                service = FoodRequestService(repository, repository, repository)
                barrier.wait(timeout=10)
                service.approve(account_id, UUID(request_id))
            return "approved"
        except BusinessError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(approve, [first["id"], second["id"]]))
    expected_error = "request_already_processed" if same_request else "insufficient_food"
    assert sorted(outcomes) == sorted(["approved", expected_error])
    with database.connect() as connection:
        assert connection.scalar(
            text("SELECT sum(quantity_kg) FROM food_requests WHERE status = 'APPROVED'")
        ) == Decimal("10")


def test_approval_waits_for_food_edit_and_uses_new_quantity(
    client, database, participants, monkeypatch
):
    donor, _, recipient, _, food = participants
    created = create_request(client, recipient, food, "10")
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
                text("UPDATE foods SET quantity_kg = 5 WHERE id = :id"), {"id": food["id"]}
            )
            approval = executor.submit(
                client.post, f"{created.headers['Location']}/approve", headers=donor
            )
            assert attempted.wait(timeout=10)
        response = approval.result(timeout=10)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "insufficient_food"
    assert client.get(created.headers["Location"], headers=recipient).json() == created.json()


def test_request_creation_and_recipient_archival_are_atomic(client, participants):
    _, _, headers, recipient, food = participants
    barrier = Barrier(2)

    def create():
        barrier.wait(timeout=10)
        return client.post(
            "/api/v1/requests", headers=headers, json={"food_id": food["id"], "quantity_kg": "1"}
        ).status_code

    def archive():
        barrier.wait(timeout=10)
        return client.delete(
            f"/api/v1/organizations/{recipient['id']}", headers=headers
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        creation, archival = executor.submit(create), executor.submit(archive)
        outcomes = creation.result(timeout=10), archival.result(timeout=10)
    assert outcomes in [(201, 409), (403, 204)]
