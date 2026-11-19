import secrets
import smtplib
import ssl
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.config import SmtpSettings
from app.infrastructure.email.smtp_recovery import SmtpRecoveryDelivery


@pytest.fixture
def smtp_settings():
    return SmtpSettings(
        _env_file=None,
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="sender@example.com",
        smtp_password=secrets.token_hex(8),
        smtp_timeout_seconds=5,
    )


@pytest.fixture
def transport(monkeypatch):
    factory = MagicMock()
    connection = factory.return_value.__enter__.return_value
    connection.send_message.return_value = {}
    monkeypatch.setattr("app.infrastructure.email.smtp_recovery.smtplib.SMTP", factory)
    return factory, connection


def test_email_uses_verified_tls_before_authentication_and_contains_only_recovery_code(
    smtp_settings, transport, caplog
):
    factory, connection = transport
    token = secrets.token_urlsafe(48)
    SmtpRecoveryDelivery(smtp_settings, 10)("recipient@example.com", token)
    factory.assert_called_once_with("smtp.example.com", 587, timeout=5)
    assert [call[0] for call in connection.mock_calls] == [
        "ehlo",
        "starttls",
        "ehlo",
        "login",
        "send_message",
    ]
    context = connection.starttls.call_args.kwargs["context"]
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    connection.login.assert_called_once_with(
        "sender@example.com", smtp_settings.smtp_password.get_secret_value()
    )
    message = connection.send_message.call_args.args[0]
    assert message["From"] == "sender@example.com"
    assert message["To"] == "recipient@example.com"
    assert token in message.get_content()
    assert "10 minutos" in message.get_content()
    assert smtp_settings.smtp_password.get_secret_value() not in message.as_string()
    assert not caplog.records


@pytest.mark.parametrize("step", ["starttls", "login", "send_message"])
def test_provider_errors_do_not_leak_secrets_or_send_without_tls(
    smtp_settings, transport, caplog, step
):
    _, connection = transport
    token = secrets.token_urlsafe(48)
    secret = smtp_settings.smtp_password.get_secret_value()
    getattr(connection, step).side_effect = smtplib.SMTPException(
        f"private provider detail: {secret} {token} recipient@example.com"
    )
    SmtpRecoveryDelivery(smtp_settings, 10)("recipient@example.com", token)
    assert [record.message for record in caplog.records] == ["Recovery email delivery failed."]
    if step == "starttls":
        connection.login.assert_not_called()
        connection.send_message.assert_not_called()
    if step == "login":
        connection.send_message.assert_not_called()


def test_network_failure_is_sanitized(smtp_settings, transport, caplog):
    factory, connection = transport
    factory.side_effect = OSError("private network error details")
    SmtpRecoveryDelivery(smtp_settings, 10)("recipient@example.com", "synthetic-token")
    connection.login.assert_not_called()
    assert [record.message for record in caplog.records] == ["Recovery email delivery failed."]


def test_refused_recipient_is_logged_without_its_address(smtp_settings, transport, caplog):
    _, connection = transport
    connection.send_message.return_value = {"recipient@example.com": (550, b"refused")}
    SmtpRecoveryDelivery(smtp_settings, 10)("recipient@example.com", "synthetic-token")
    assert [record.message for record in caplog.records] == ["Recovery email delivery failed."]


def test_header_injection_does_not_open_smtp_connection(smtp_settings, transport, caplog):
    factory, _ = transport
    SmtpRecoveryDelivery(smtp_settings, 10)(
        "recipient@example.com\r\nBcc: other@example.com", "code"
    )
    factory.assert_not_called()
    assert [record.message for record in caplog.records] == ["Recovery email delivery failed."]


@pytest.mark.parametrize(
    "field,value",
    [
        ("smtp_host", ""),
        ("smtp_host", "host\nname"),
        ("smtp_port", 0),
        ("smtp_port", 65536),
        ("smtp_username", "invalid"),
        ("smtp_password", "short"),
        ("smtp_password", "x" * 17),
        ("smtp_password", "é" * 16),
        ("smtp_password", "x" * 15 + "\n"),
        ("smtp_timeout_seconds", 0),
        ("smtp_timeout_seconds", 61),
        ("smtp_timeout_seconds", float("inf")),
        ("smtp_timeout_seconds", float("nan")),
    ],
)
def test_invalid_smtp_configuration_fails_before_network_access(
    smtp_settings, transport, field, value
):
    values = smtp_settings.model_dump()
    values[field] = value
    with pytest.raises(ValidationError):
        SmtpSettings(_env_file=None, **values)
    transport[0].assert_not_called()


def test_display_spaces_in_app_password_are_normalized(smtp_settings):
    values = smtp_settings.model_dump()
    original = smtp_settings.smtp_password.get_secret_value()
    values["smtp_password"] = " ".join(original[index : index + 4] for index in range(0, 16, 4))
    parsed = SmtpSettings(_env_file=None, **values)
    assert parsed.smtp_password.get_secret_value() == original
    assert original not in repr(parsed)


def test_startup_validation_error_does_not_print_invalid_secret(smtp_settings):
    values = smtp_settings.model_dump()
    invalid_secret = secrets.token_hex(20)
    values["smtp_password"] = invalid_secret
    with pytest.raises(ValidationError) as error:
        SmtpSettings(_env_file=None, **values)
    assert invalid_secret not in str(error.value)
