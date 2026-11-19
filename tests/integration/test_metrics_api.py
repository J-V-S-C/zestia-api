from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.infrastructure.persistence.orm import (
    AccountRecord,
    FoodRecord,
    FoodRequestRecord,
    OrganizationRecord,
)
from tests.integration.test_food_api import food_payload, organization, sign_in

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


def counts(total=0, requested="0.000", approved="0.000", pending=0, accepted=0, rejected=0):
    return {
        "total_requests": total,
        "requested_food_kg": requested,
        "approved_food_kg": approved,
        "pending_requests": pending,
        "approved_requests": accepted,
        "rejected_requests": rejected,
    }


@pytest.fixture
def stored_metrics(client, database):
    headers = sign_in(client, "metrics-reader@example.com")
    ids = [uuid4() for _ in range(4)]
    foods = [uuid4() for _ in range(4)]
    with Session(database) as session, session.begin():
        for index, org_id in enumerate(ids):
            owner = uuid4()
            session.add(
                AccountRecord(
                    id=owner,
                    email=f"metrics-{index}@example.com",
                    password_hash="unused-test-fixture-hash",
                    role="USER",
                )
            )
            session.flush()
            session.add(
                OrganizationRecord(
                    id=org_id,
                    owner_account_id=owner,
                    name=["Alpha", "Beta", "Gamma", "Unused"][index],
                    type="NGO",
                    location="Test fixture",
                )
            )
        session.flush()
        for food_id, donor, quantity in zip(
            foods,
            [ids[0], ids[0], ids[1], ids[2]],
            ["10.125", "2.250", "8.375", "1.000"],
            strict=True,
        ):
            session.add(
                FoodRecord(
                    id=food_id,
                    donor_organization_id=donor,
                    name="Historical fixture",
                    category="Grains",
                    quantity_kg=Decimal(quantity),
                    expiration_date=date.min,
                )
            )
        session.flush()
        for food, recipient, quantity, status in [
            (0, 1, "1.125", "PENDING"),
            (0, 1, "2.250", "APPROVED"),
            (0, 2, "3.125", "APPROVED"),
            (1, 2, "1.500", "REJECTED"),
            (2, 0, "4.375", "APPROVED"),
            (2, 2, "0.625", "PENDING"),
        ]:
            session.add(
                FoodRequestRecord(
                    id=uuid4(),
                    food_id=foods[food],
                    recipient_organization_id=ids[recipient],
                    quantity_kg=Decimal(quantity),
                    status=status,
                )
            )
    return headers, ids, foods


def test_empty_metrics_are_zero_and_require_no_owned_organization(client):
    headers = sign_in(client)
    response = client.get("/api/v1/metrics", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "total_organizations": 0,
        "registered_food_kg": "0.000",
        "requests": counts(),
    }
    assert client.get("/api/v1/metrics/organizations", headers=headers).json() == []


def test_totals_count_each_food_and_request_once_and_preserve_decimal_kg(client, stored_metrics):
    headers, _, _ = stored_metrics
    response = client.get("/api/v1/metrics", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "total_organizations": 4,
        "registered_food_kg": "21.750",
        "requests": counts(6, "13.000", "9.750", 2, 3, 1),
    }


@pytest.mark.parametrize(
    "status,expected",
    [
        ("PENDING", counts(2, "1.750", "0.000", 2)),
        ("APPROVED", counts(3, "9.750", "9.750", accepted=3)),
        ("REJECTED", counts(1, "1.500", "0.000", rejected=1)),
    ],
)
def test_status_filter_only_changes_request_figures(client, stored_metrics, status, expected):
    headers, _, _ = stored_metrics
    result = client.get(f"/api/v1/metrics?status={status}", headers=headers).json()
    assert result == {
        "total_organizations": 4,
        "registered_food_kg": "21.750",
        "requests": expected,
    }


def test_organization_filter_counts_both_roles_without_duplicate_requests(client, stored_metrics):
    headers, ids, _ = stored_metrics
    result = client.get(f"/api/v1/metrics?organization_id={ids[0]}", headers=headers).json()
    assert result == {
        "total_organizations": 1,
        "registered_food_kg": "12.375",
        "requests": counts(5, "12.375", "9.750", 1, 3, 1),
    }
    result = client.get(
        f"/api/v1/metrics?organization_id={ids[0]}&status=PENDING", headers=headers
    ).json()
    assert result["requests"] == counts(1, "1.125", "0.000", 1)
    assert result["registered_food_kg"] == "12.375"


def test_organization_breakdown_separates_donation_and_recipient_roles(client, stored_metrics):
    headers, ids, _ = stored_metrics
    result = client.get("/api/v1/metrics/organizations", headers=headers)
    assert result.status_code == 200, result.text
    rows = result.json()
    assert [row["organization_id"] for row in rows] == [str(value) for value in ids]
    assert rows[0] == {
        "organization_id": str(ids[0]),
        "organization_name": "Alpha",
        "registered_food_kg": "12.375",
        "donation_requests": counts(4, "8.000", "5.375", 1, 2, 1),
        "recipient_requests": counts(1, "4.375", "4.375", accepted=1),
    }
    assert rows[1]["donation_requests"] == counts(2, "5.000", "4.375", 1, 1)
    assert rows[1]["recipient_requests"] == counts(2, "3.375", "2.250", 1, 1)
    assert rows[2]["registered_food_kg"] == "1.000"
    assert rows[2]["donation_requests"] == counts()
    assert rows[2]["recipient_requests"] == counts(3, "5.250", "3.125", 1, 1, 1)
    assert rows[3]["donation_requests"] == rows[3]["recipient_requests"] == counts()
    assert sum(Decimal(row["registered_food_kg"]) for row in rows) == Decimal("21.750")
    assert sum(row["donation_requests"]["total_requests"] for row in rows) == 6
    assert sum(row["recipient_requests"]["total_requests"] for row in rows) == 6


@pytest.mark.parametrize("status", ["PENDING", "APPROVED", "REJECTED"])
def test_grouped_filters_apply_before_pagination_and_totals_are_unpaginated(
    client, stored_metrics, status
):
    headers, ids, _ = stored_metrics
    path = f"/api/v1/metrics/organizations?organization_id={ids[2]}&status={status}"
    rows = client.get(f"{path}&limit=1", headers=headers).json()
    assert len(rows) == 1
    assert rows[0]["organization_id"] == str(ids[2])
    assert rows[0]["donation_requests"] == counts()
    assert rows[0]["recipient_requests"]["total_requests"] == 1
    assert rows[0]["registered_food_kg"] == "1.000"
    assert client.get(f"{path}&offset=1", headers=headers).json() == []
    pages = [
        client.get(f"/api/v1/metrics/organizations?limit=1&offset={offset}", headers=headers).json()
        for offset in range(4)
    ]
    assert [page[0]["organization_id"] for page in pages] == [str(value) for value in ids]
    assert client.get("/api/v1/metrics", headers=headers).json()["requests"]["total_requests"] == 6


def test_unknown_and_archived_organizations_do_not_appear_in_counts_or_groups(
    client, database, stored_metrics
):
    headers, ids, _ = stored_metrics
    with database.begin() as connection:
        connection.execute(
            text("UPDATE organizations SET deleted_at = now() WHERE id = :id"), {"id": ids[3]}
        )
    assert client.get("/api/v1/metrics", headers=headers).json()["total_organizations"] == 3
    assert len(client.get("/api/v1/metrics/organizations", headers=headers).json()) == 3
    for org_id in [ids[3], uuid4()]:
        assert client.get(f"/api/v1/metrics?organization_id={org_id}", headers=headers).json() == {
            "total_organizations": 0,
            "registered_food_kg": "0.000",
            "requests": counts(),
        }
        assert (
            client.get(
                f"/api/v1/metrics/organizations?organization_id={org_id}", headers=headers
            ).json()
            == []
        )


@pytest.mark.parametrize("path", ["/api/v1/metrics", "/api/v1/metrics/organizations"])
def test_metrics_require_authentication_and_reject_revoked_sessions(client, path):
    assert client.get(path).status_code == 401
    headers = sign_in(client)
    assert client.get(path, headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get(path, headers=headers).status_code == 401


@pytest.mark.parametrize("path", ["/api/v1/metrics", "/api/v1/metrics/organizations"])
@pytest.mark.parametrize("query", ["organization_id=bad", "status=DELIVERED"])
def test_invalid_filters_are_rejected(client, path, query):
    assert client.get(f"{path}?{query}", headers=sign_in(client)).status_code == 422


@pytest.mark.parametrize("query", ["offset=-1", "limit=0", "limit=101"])
def test_invalid_group_pagination_is_rejected(client, query):
    assert (
        client.get(f"/api/v1/metrics/organizations?{query}", headers=sign_in(client)).status_code
        == 422
    )


def test_aggregates_are_platform_visible_but_do_not_expose_private_request_records(
    client, stored_metrics
):
    headers, _, _ = stored_metrics
    assert client.get("/api/v1/requests", headers=headers).json() == []
    result = client.get("/api/v1/metrics", headers=headers).json()
    assert result["requests"]["total_requests"] == 6
    assert set(result["requests"]) == set(counts())


def test_aggregate_quantities_can_exceed_individual_listing_limit(client, database, stored_metrics):
    headers, _, _ = stored_metrics
    with database.begin() as connection:
        connection.execute(text("UPDATE foods SET quantity_kg = 999999999.999"))
    assert (
        client.get("/api/v1/metrics", headers=headers).json()["registered_food_kg"]
        == "3999999999.996"
    )


def test_metrics_reflect_committed_api_changes_without_reducing_registered_quantity(client):
    donor = sign_in(client)
    donor_org = organization(client, donor)
    recipient = sign_in(client, "metrics-recipient@example.com")
    organization(client, recipient)
    food = client.post("/api/v1/foods", headers=donor, json=food_payload()).json()
    response = client.post(
        "/api/v1/requests", headers=recipient, json={"food_id": food["id"], "quantity_kg": "2.125"}
    )
    assert response.status_code == 201
    path = response.headers["Location"]
    before = client.get("/api/v1/metrics", headers=donor).json()
    assert before["requests"] == counts(1, "2.125", "0.000", 1)
    assert client.post(f"{path}/approve", headers=donor).status_code == 200
    after = client.get("/api/v1/metrics", headers=recipient).json()
    assert after["requests"] == counts(1, "2.125", "2.125", accepted=1)
    assert after["registered_food_kg"] == before["registered_food_kg"] == "12.125"
    assert client.post(f"{path}/reject", headers=donor).status_code == 409
    assert client.get("/api/v1/metrics", headers=donor).json() == after
    assert (
        client.put(
            f"/api/v1/foods/{food['id']}",
            headers=donor,
            json={**food_payload(), "quantity_kg": "3.000"},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/metrics", headers=donor).json()["registered_food_kg"] == "3.000"
    grouped = client.get(
        f"/api/v1/metrics/organizations?organization_id={donor_org['id']}", headers=recipient
    ).json()
    assert grouped[0]["donation_requests"] == after["requests"]


def test_each_aggregate_response_uses_one_sql_snapshot(client, database, stored_metrics):
    headers, _, _ = stored_metrics
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if "foods" in statement and "food_requests" in statement:
            statements.append(statement)

    event.listen(client.app.state.engine, "before_cursor_execute", capture)
    try:
        for path in ["/api/v1/metrics", "/api/v1/metrics/organizations"]:
            statements.clear()
            assert client.get(path, headers=headers).status_code == 200
            assert len(statements) == 1
    finally:
        event.remove(client.app.state.engine, "before_cursor_execute", capture)
