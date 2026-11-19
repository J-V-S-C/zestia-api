import pytest

from app.config import AdminBootstrapSettings, RecoverySettings, Settings, SmtpSettings


@pytest.fixture(autouse=True)
def disable_private_configuration_files(monkeypatch):
    # Tests use explicit values/environment fixtures, never the developer's private file.
    # Configuration-file tests pass their own synthetic fixture path explicitly.
    for settings in (Settings, AdminBootstrapSettings, RecoverySettings, SmtpSettings):
        monkeypatch.setitem(settings.model_config, "env_file", None)
