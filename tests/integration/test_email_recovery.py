import secrets
import smtplib
from hashlib import sha256
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.main import create_app
from tests.integration.test_lifecycle import login

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


@pytest.fixture
def smtp_configuration(monkeypatch):
    values = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USERNAME": "sender@example.com",
        "SMTP_PASSWORD": secrets.token_hex(8),
        "SMTP_TIMEOUT_SECONDS": "5",
        "RECOVERY_TOKEN_MINUTES": "10",
        "RECOVERY_WINDOW_SECONDS": "60",
        "RECOVERY_MAX_ATTEMPTS": "20",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    transport = MagicMock()
    transport.return_value.__enter__.return_value.send_message.return_value = {}
    monkeypatch.setattr("app.infrastructure.email.smtp_recovery.smtplib.SMTP", transport)
    return transport


def test_gmail_adapter_restores_account_and_delivery_runs_after_commit(
    client, database, smtp_configuration
):
    body, headers = login(client, "smtp-recovery@example.com")
    account_id = client.get("/api/v1/auth/me", headers=headers).json()["id"]
    assert client.delete("/api/v1/auth/me", headers=headers).status_code == 204
    tokens = []

    def receive(message):
        token = next(line for line in message.get_content().splitlines() if len(line) == 64)
        assert message["To"] == body["email"]
        with database.connect() as connection:
            assert (
                connection.scalar(text("SELECT token_hash FROM account_recovery"))
                == sha256(token.encode()).hexdigest()
            )
        tokens.append(token)
        return {}

    smtp_configuration.return_value.__enter__.return_value.send_message.side_effect = receive
    settings = client.app.state.settings.model_copy(update={"recovery_email_enabled": True})
    with TestClient(create_app(settings)) as smtp_api:
        known = smtp_api.post("/api/v1/auth/recovery/request", json={"email": body["email"]})
        unknown = smtp_api.post(
            "/api/v1/auth/recovery/request", json={"email": "unknown@example.com"}
        )
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        assert len(tokens) == 1
        assert tokens[0] not in known.text
        assert (
            smtp_api.post("/api/v1/auth/recovery/confirm", json={"token": tokens[0]}).status_code
            == 204
        )
        assert smtp_api.get("/api/v1/auth/me", headers=headers).status_code == 401
        assert (
            smtp_api.post("/api/v1/auth/recovery/confirm", json={"token": tokens[0]}).status_code
            == 422
        )
        authenticated = smtp_api.post("/api/v1/auth/login", json=body)
        assert authenticated.status_code == 200
        new_headers = {"Authorization": "Bearer " + authenticated.json()["access_token"]}
        assert smtp_api.get("/api/v1/auth/me", headers=new_headers).json()["id"] == account_id


def test_smtp_failure_keeps_generic_response_and_sanitized_logs(client, smtp_configuration, caplog):
    body, headers = login(client, "smtp-failure@example.com")
    assert client.delete("/api/v1/auth/me", headers=headers).status_code == 204
    smtp_configuration.side_effect = smtplib.SMTPAuthenticationError(
        535, b"private-provider-detail"
    )
    settings = client.app.state.settings.model_copy(update={"recovery_email_enabled": True})
    with TestClient(create_app(settings)) as smtp_api:
        known = smtp_api.post("/api/v1/auth/recovery/request", json={"email": body["email"]})
        unknown = smtp_api.post(
            "/api/v1/auth/recovery/request", json={"email": "unknown@example.com"}
        )
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
    errors = [record.message for record in caplog.records if record.levelname == "ERROR"]
    assert errors == ["Recovery email delivery failed."]


@pytest.mark.parametrize(
    "missing",
    [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_TIMEOUT_SECONDS",
        "RECOVERY_TOKEN_MINUTES",
    ],
)
def test_enabled_smtp_requires_complete_configuration_before_startup(
    client, smtp_configuration, monkeypatch, missing
):
    monkeypatch.delenv(missing)
    settings = client.app.state.settings.model_copy(update={"recovery_email_enabled": True})
    with pytest.raises(ValidationError):
        create_app(settings)
    smtp_configuration.assert_not_called()


def test_disabled_delivery_and_injected_delivery_never_connect_to_smtp(client, smtp_configuration):
    with TestClient(create_app(client.app.state.settings)) as disabled:
        assert disabled.app.state.recovery_delivery is None
    settings = client.app.state.settings.model_copy(update={"recovery_email_enabled": True})
    messages = []

    def delivery(email, token):
        messages.append((email, token))

    with TestClient(create_app(settings, recovery_delivery=delivery)) as injected:
        assert injected.app.state.recovery_delivery is delivery
    smtp_configuration.assert_not_called()
