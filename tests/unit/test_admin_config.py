import pytest
from pydantic import ValidationError

from app.config import AdminBootstrapSettings


@pytest.mark.parametrize("password", ["short", "replace-with-a-generated-password"])
def test_admin_bootstrap_rejects_weak_or_placeholder_password(password):
    with pytest.raises(ValidationError):
        AdminBootstrapSettings(
            _env_file=None, admin_email="operator@example.com", admin_password=password
        )


def test_admin_bootstrap_requires_private_environment_credentials(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with pytest.raises(ValidationError) as error:
        AdminBootstrapSettings(_env_file=None)
    assert {item["loc"][0] for item in error.value.errors()} == {
        "admin_email",
        "admin_password",
    }
