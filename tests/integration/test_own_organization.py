import pytest
from sqlalchemy import text

from tests.integration.test_api import organization_payload, sign_in

pytestmark = [pytest.mark.integration, pytest.mark.e2e]
PATH = "/api/v1/auth/me/organization"


def create_organization(client, headers, name):
    response = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={**organization_payload(), "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_account_without_organization_cannot_select_another_owners_organization(client):
    owner = sign_in(client)
    organization = create_organization(client, owner, "Synthetic owner organization")
    owner_id = client.get("/api/v1/auth/me", headers=owner).json()["id"]
    other = sign_in(client, "other@example.com")

    response = client.get(
        PATH,
        headers=other,
        params={"account_id": owner_id, "organization_id": organization["id"]},
    )
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "organization_not_found",
            "message": "The account has no active organization.",
        }
    }


@pytest.mark.parametrize("status", ["PENDING", "VERIFIED", "REJECTED", "SUSPENDED"])
def test_logged_in_account_gets_only_its_organization_in_every_review_state(
    client, database, status
):
    owner = sign_in(client)
    organization = create_organization(client, owner, "Synthetic owner organization")
    other = sign_in(client, "other@example.com")
    other_organization = create_organization(client, other, "Synthetic other organization")
    other_id = client.get("/api/v1/auth/me", headers=other).json()["id"]
    with database.begin() as connection:
        connection.execute(
            text("UPDATE organizations SET verification_status = :status WHERE id = :id"),
            {"status": status, "id": organization["id"]},
        )

    response = client.get(
        PATH,
        headers=owner,
        params={"account_id": other_id, "organization_id": other_organization["id"]},
    )
    assert response.status_code == 200
    assert response.json() == {**organization, "verification_status": status}
    assert set(response.json()) == {
        "id",
        "name",
        "type",
        "location",
        "verification_status",
        "deleted_at",
    }
    assert client.get(PATH, headers=other).json() == other_organization


def test_archived_organization_is_hidden_and_active_replacement_is_returned(client):
    headers = sign_in(client)
    previous = create_organization(client, headers, "Synthetic archived organization")
    assert (
        client.delete(f"/api/v1/organizations/{previous['id']}", headers=headers).status_code == 204
    )
    assert client.get(PATH, headers=headers).status_code == 404

    replacement = create_organization(client, headers, "Synthetic replacement organization")
    response = client.get(PATH, headers=headers)
    assert response.status_code == 200
    assert response.json() == replacement
    assert replacement["id"] != previous["id"]
    archived = client.get("/api/v1/auth/me/organizations/archived", headers=headers)
    assert archived.status_code == 200
    assert [organization["id"] for organization in archived.json()] == [previous["id"]]


@pytest.mark.parametrize("authentication", ["missing", "malformed", "logged_out", "closed"])
def test_own_organization_requires_an_active_authenticated_session(client, authentication):
    headers = sign_in(client)
    create_organization(client, headers, "Synthetic private organization")
    if authentication == "missing":
        headers = {}
    elif authentication == "malformed":
        headers = {"Authorization": "Bearer malformed"}
    elif authentication == "logged_out":
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    else:
        assert client.delete("/api/v1/auth/me", headers=headers).status_code == 204

    assert client.get(PATH, headers=headers).status_code == 401
