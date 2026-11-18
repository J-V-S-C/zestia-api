from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from threading import Barrier

import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


def login(client, email):
    body = {"email": email, "password": "password8"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 201
    response = client.post("/api/v1/auth/login", json=body)
    assert response.status_code == 200
    return body, {"Authorization": "Bearer " + response.json()["access_token"]}


def create_org(client, headers):
    response = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "Review fixture", "type": "NGO", "location": "Centro"},
    )
    assert response.status_code == 201
    return response.json()


def test_logout_revokes_only_current_session_and_persists(client):
    body, first = login(client, "logout@example.com")
    second = {
        "Authorization": "Bearer "
        + client.post("/api/v1/auth/login", json=body).json()["access_token"]
    }
    assert first != second
    assert client.post("/api/v1/auth/logout", headers=first).status_code == 204
    assert client.get("/api/v1/auth/me", headers=first).status_code == 401
    assert client.get("/api/v1/auth/me", headers=second).status_code == 200
    client.app.state.engine.dispose()  # Force fresh database connections.
    assert client.get("/api/v1/auth/me", headers=first).status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 401


@pytest.fixture
def recovery(client, monkeypatch):
    monkeypatch.setenv("RECOVERY_TOKEN_MINUTES", "10")
    monkeypatch.setenv("RECOVERY_WINDOW_SECONDS", "60")
    monkeypatch.setenv("RECOVERY_MAX_ATTEMPTS", "20")
    messages = []
    client.app.state.recovery_delivery = lambda email, token: messages.append((email, token))
    return messages


def test_recovery_retains_identity_requires_new_login_and_invalidates_every_old_token(
    client, database, recovery
):
    body, headers = login(client, "restore@example.com")
    account_id = client.get("/api/v1/auth/me", headers=headers).json()["id"]
    organization = create_org(client, headers)
    assert client.delete("/api/v1/auth/me", headers=headers).status_code == 204
    known = client.post("/api/v1/auth/recovery/request", json={"email": body["email"]})
    unknown = client.post("/api/v1/auth/recovery/request", json={"email": "unknown@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    token = recovery[0][1]
    with database.connect() as connection:
        assert (
            connection.scalar(text("SELECT token_hash FROM account_recovery"))
            == sha256(token.encode()).hexdigest()
        )
    assert client.post("/api/v1/auth/recovery/confirm", json={"token": token}).status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    fresh = client.post("/api/v1/auth/login", json=body)
    assert fresh.status_code == 200
    fresh_headers = {"Authorization": "Bearer " + fresh.json()["access_token"]}
    assert client.get("/api/v1/auth/me", headers=fresh_headers).json()["id"] == account_id
    assert client.get("/api/v1/organizations", headers=fresh_headers).json() == []
    restored = client.post(
        f"/api/v1/organizations/{organization['id']}/restore", headers=fresh_headers
    )
    assert restored.status_code == 200
    assert restored.json()["id"] == organization["id"]
    assert client.post("/api/v1/auth/recovery/confirm", json={"token": token}).status_code == 422
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_external_delivery_is_explicitly_unavailable(client, recovery):
    client.app.state.recovery_delivery = None
    for email in ["unknown@example.com", "other@example.com"]:
        assert (
            client.post("/api/v1/auth/recovery/request", json={"email": email}).status_code == 503
        )


@pytest.mark.parametrize("kind", ["invalid", "expired", "concurrent"])
def test_recovery_rejects_invalid_expired_and_concurrently_reused_tokens(
    client, database, recovery, kind
):
    body, headers = login(client, "tokens@example.com")
    assert client.delete("/api/v1/auth/me", headers=headers).status_code == 204
    assert (
        client.post("/api/v1/auth/recovery/request", json={"email": body["email"]}).status_code
        == 202
    )
    token = recovery[0][1]
    if kind == "invalid":
        assert (
            client.post("/api/v1/auth/recovery/confirm", json={"token": "invalid"}).status_code
            == 422
        )
    elif kind == "expired":
        with database.begin() as connection:
            connection.execute(
                text("UPDATE account_recovery SET expires_at = :expired"),
                {"expired": datetime.now(UTC) - timedelta(minutes=1)},
            )
        assert (
            client.post("/api/v1/auth/recovery/confirm", json={"token": token}).status_code == 422
        )
    else:
        barrier = Barrier(2)

        def confirm(_):
            barrier.wait(timeout=10)
            return client.post("/api/v1/auth/recovery/confirm", json={"token": token}).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(confirm, range(2))) == [204, 422]


def test_recovery_rate_limit_survives_failed_confirmation(client, recovery, monkeypatch):
    monkeypatch.setenv("RECOVERY_MAX_ATTEMPTS", "2")
    for _ in range(2):
        assert (
            client.post("/api/v1/auth/recovery/confirm", json={"token": "bad"}).status_code == 422
        )
    assert client.post("/api/v1/auth/recovery/confirm", json={"token": "bad"}).status_code == 429


def test_restore_owner_conflict_and_concurrency(client):
    _, headers = login(client, "org-owner@example.com")
    _, other = login(client, "not-owner@example.com")
    organization = create_org(client, headers)
    path = f"/api/v1/organizations/{organization['id']}"
    assert client.delete(path, headers=headers).status_code == 204
    assert client.post(path + "/restore", headers=other).status_code == 403
    replacement = create_org(client, headers)
    assert client.post(path + "/restore", headers=headers).status_code == 409
    assert (
        client.delete(f"/api/v1/organizations/{replacement['id']}", headers=headers).status_code
        == 204
    )
    barrier = Barrier(2)

    def restore(_):
        barrier.wait(timeout=10)
        return client.post(path + "/restore", headers=headers).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(restore, range(2))) == [200, 409]


def test_verification_permissions_evidence_transitions_and_donation_gate(client, database):
    _, owner = login(client, "org@example.com")
    _, admin = login(client, "admin@example.com")
    with database.begin() as connection:
        connection.execute(
            text("UPDATE accounts SET role = 'ADMIN' WHERE email = 'admin@example.com'")
        )
    organization = create_org(client, owner)
    assert organization["verification_status"] == "PENDING"
    path = f"/api/v1/organizations/{organization['id']}/verification"
    decision = {"status": "VERIFIED", "reason": "Representation and supporting evidence reviewed."}
    food = {
        "name": "Rice",
        "category": "Grains",
        "quantity_kg": "1",
        "expiration_date": "9999-12-31",
    }
    assert client.post("/api/v1/foods", headers=owner, json=food).status_code == 403
    assert client.post(path + "/review", headers=owner, json=decision).status_code == 403
    assert client.post(path + "/review", headers=admin, json=decision).status_code == 409
    evidence = "Community kitchen reference and official contact for manual review."
    assert client.post(path, headers=owner, json={"evidence": evidence}).status_code == 200
    assert client.get(path, headers=owner).status_code == 403
    assert client.get(path, headers=admin).json()["evidence"] == evidence
    assert client.post(path + "/review", headers=admin, json=decision).status_code == 200
    published = client.post("/api/v1/foods", headers=owner, json=food)
    assert published.status_code == 201
    assert (
        client.post(
            path + "/review", headers=admin, json={**decision, "status": "SUSPENDED"}
        ).status_code
        == 200
    )
    assert client.post("/api/v1/foods", headers=owner, json=food).status_code == 403
    assert client.post(path, headers=owner, json={"evidence": evidence}).status_code == 409
    assert client.put(published.headers["Location"], headers=owner, json=food).status_code == 403
    assert client.delete(published.headers["Location"], headers=owner).status_code == 204
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM lifecycle_events")) == 3


def test_verified_identity_change_requires_new_review_and_no_self_review(client, database):
    _, owner = login(client, "identity@example.com")
    organization = create_org(client, owner)
    with database.begin() as connection:
        connection.execute(text("UPDATE organizations SET verification_status = 'VERIFIED'"))
        connection.execute(text("UPDATE accounts SET role = 'ADMIN'"))
    path = f"/api/v1/organizations/{organization['id']}"
    changed = client.put(
        path, headers=owner, json={"name": "Changed identity", "type": "NGO", "location": "Centro"}
    )
    assert changed.json()["verification_status"] == "PENDING"
    assert (
        client.post(
            path + "/verification/review",
            headers=owner,
            json={"status": "VERIFIED", "reason": "Self approval attempt"},
        ).status_code
        == 403
    )


def test_archives_are_owner_scoped_and_restoration_preserves_suspension(client, database):
    _, owner = login(client, "archives@example.com")
    _, other = login(client, "other-archives@example.com")
    organization = create_org(client, owner)
    with database.begin() as connection:
        connection.execute(text("UPDATE organizations SET verification_status = 'SUSPENDED'"))
    path = f"/api/v1/organizations/{organization['id']}"
    assert client.delete(path, headers=owner).status_code == 204
    archived = client.get("/api/v1/auth/me/organizations/archived", headers=owner).json()
    assert archived[0]["id"] == organization["id"]
    assert archived[0]["deleted_at"] is not None
    assert client.get("/api/v1/auth/me/organizations/archived", headers=other).json() == []
    assert (
        client.get("/api/v1/auth/me/organizations/archived?offset=-1", headers=owner).status_code
        == 422
    )
    restored = client.post(path + "/restore", headers=owner)
    assert restored.json()["verification_status"] == "SUSPENDED"


def test_recovery_consumes_all_links_even_across_a_second_closure(client, recovery):
    body, headers = login(client, "multiple-links@example.com")
    assert client.delete("/api/v1/auth/me", headers=headers).status_code == 204
    for _ in range(2):
        assert (
            client.post("/api/v1/auth/recovery/request", json={"email": body["email"]}).status_code
            == 202
        )
    first, second = recovery[0][1], recovery[1][1]
    assert client.post("/api/v1/auth/recovery/confirm", json={"token": first}).status_code == 204
    fresh = {
        "Authorization": "Bearer "
        + client.post("/api/v1/auth/login", json=body).json()["access_token"]
    }
    assert client.delete("/api/v1/auth/me", headers=fresh).status_code == 204
    for token in [first, second]:
        assert (
            client.post("/api/v1/auth/recovery/confirm", json={"token": token}).status_code == 422
        )


def test_recovery_active_account_generic_response_and_bad_configuration(
    client, recovery, monkeypatch
):
    body, _ = login(client, "active-recovery@example.com")
    response = client.post("/api/v1/auth/recovery/request", json={"email": body["email"]})
    assert response.status_code == 202
    assert recovery == []
    monkeypatch.setenv("RECOVERY_TOKEN_MINUTES", "0")
    assert (
        client.post("/api/v1/auth/recovery/request", json={"email": body["email"]}).status_code
        == 503
    )


def test_verification_rejection_resubmission_and_identity_change_discard_old_evidence(
    client, database
):
    _, owner = login(client, "review-flow@example.com")
    _, admin = login(client, "review-flow-admin@example.com")
    with database.begin() as connection:
        connection.execute(
            text("UPDATE accounts SET role = 'ADMIN' WHERE email = 'review-flow-admin@example.com'")
        )
    organization = create_org(client, owner)
    path = f"/api/v1/organizations/{organization['id']}"
    evidence = "Official contact and community reference for this organization."
    assert (
        client.post(path + "/verification", headers=admin, json={"evidence": evidence}).status_code
        == 403
    )
    assert (
        client.post(path + "/verification", headers=owner, json={"evidence": evidence}).status_code
        == 200
    )
    decision = {"status": "REJECTED", "reason": "Supporting evidence is insufficient."}
    assert (
        client.post(path + "/verification/review", headers=admin, json=decision).status_code == 200
    )
    assert (
        client.post(path + "/verification", headers=owner, json={"evidence": evidence}).json()[
            "verification_status"
        ]
        == "PENDING"
    )
    decision["status"] = "VERIFIED"
    assert (
        client.post(path + "/verification/review", headers=admin, json=decision).status_code == 200
    )
    assert (
        client.post(path + "/verification", headers=owner, json={"evidence": evidence}).status_code
        == 409
    )
    assert (
        client.post(path + "/verification/review", headers=admin, json=decision).status_code == 409
    )
    changed = client.put(
        path, headers=owner, json={"name": "New identity", "type": "NGO", "location": "Centro"}
    )
    assert changed.json()["verification_status"] == "PENDING"
    assert client.get(path + "/verification", headers=admin).json()["evidence"] is None
    assert (
        client.post(path + "/verification/review", headers=admin, json=decision).status_code == 409
    )


def test_concurrent_restore_and_replacement_preserve_single_active_organization(client):
    _, headers = login(client, "restore-race@example.com")
    organization = create_org(client, headers)
    path = f"/api/v1/organizations/{organization['id']}"
    assert client.delete(path, headers=headers).status_code == 204
    barrier = Barrier(2)

    def restore():
        barrier.wait(timeout=10)
        return client.post(path + "/restore", headers=headers).status_code

    def create():
        barrier.wait(timeout=10)
        return client.post(
            "/api/v1/organizations",
            headers=headers,
            json={"name": "Replacement", "type": "NGO", "location": "Centro"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        restoring, creating = executor.submit(restore), executor.submit(create)
        assert (restoring.result(), creating.result()) in [(200, 409), (409, 201)]
    assert len(client.get("/api/v1/organizations", headers=headers).json()) == 1
