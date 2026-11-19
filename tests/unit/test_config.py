import json

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture
def configuration():
    return {
        "database_url": "postgresql+psycopg://test-user:test-password@db.zestia.test:5433/test_db",
        "jwt_secret": "test-secret-at-least-32-characters-long",
        "jwt_issuer": "zestia-test",
        "jwt_audience": "zestia-test-api",
        "access_token_minutes": 27,
        "cors_origins": ["https://frontend.zestia.test"],
        "admin_email": "reserved-admin@example.com",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"jwt_secret": "short"},
        {"jwt_secret": "replace-with-a-long-but-placeholder-secret"},
        {"database_url": "sqlite:///database.db"},
        {"access_token_minutes": 0},
        {"access_token_minutes": 1441},
        {"jwt_issuer": ""},
        {"jwt_audience": ""},
        {"admin_email": "invalid-email"},
    ],
)
def test_invalid_configuration_fails_before_serving_requests(configuration, overrides):
    values = {**configuration, **overrides}
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **values)
    assert {item["loc"][0] for item in error.value.errors()} == set(overrides)


def test_missing_environment_settings_fail_without_fallbacks():
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)
    assert {item["loc"][0] for item in error.value.errors()} == {
        "database_url",
        "jwt_secret",
        "jwt_issuer",
        "jwt_audience",
        "access_token_minutes",
        "cors_origins",
        "admin_email",
    }
    assert all(item["type"] == "missing" for item in error.value.errors())


@pytest.mark.parametrize("source", ["environment", "dotenv"])
def test_loads_explicit_configuration(configuration, source, monkeypatch, tmp_path):
    environment = {
        name.upper(): json.dumps(value) if isinstance(value, list) else str(value)
        for name, value in configuration.items()
    }
    if source == "environment":
        for name, value in environment.items():
            monkeypatch.setenv(name, value)
        settings = Settings(_env_file=None)
    else:
        env_file = tmp_path / "settings.fixture"
        env_file.write_text("\n".join(f"{name}={value}" for name, value in environment.items()))
        settings = Settings(_env_file=env_file)
    assert settings.database_url == configuration["database_url"]
    assert settings.jwt_secret.get_secret_value() == configuration["jwt_secret"]
    assert settings.jwt_issuer == configuration["jwt_issuer"]
    assert settings.jwt_audience == configuration["jwt_audience"]
    assert settings.access_token_minutes == configuration["access_token_minutes"]
    assert settings.cors_origins == configuration["cors_origins"]


def test_environment_overrides_dotenv(configuration, monkeypatch, tmp_path):
    env_file = tmp_path / "settings.fixture"
    env_file.write_text("JWT_ISSUER=dotenv-issuer\n")
    monkeypatch.setenv("JWT_ISSUER", "environment-issuer")
    del configuration["jwt_issuer"]
    assert Settings(_env_file=env_file, **configuration).jwt_issuer == "environment-issuer"
