from pathlib import Path

from pydantic import EmailStr, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parents[1] / ".env", extra="ignore", hide_input_in_errors=True
    )
    database_url: str
    jwt_secret: SecretStr
    jwt_issuer: str = Field(min_length=1)
    jwt_audience: str = Field(min_length=1)
    access_token_minutes: int = Field(ge=1, le=1440)
    cors_origins: list[str]
    admin_email: EmailStr
    recovery_email_enabled: bool = False

    @field_validator("jwt_secret")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32 or secret.startswith("replace-"):
            raise ValueError(
                "Set JWT_SECRET to a generated random secret of at least 32 characters."
            )
        return value

    @field_validator("database_url")
    @classmethod
    def validate_driver(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("Use a postgresql+psycopg database URL.")
        return value


class RecoverySettings(BaseSettings):
    model_config = Settings.model_config
    recovery_token_minutes: int = Field(ge=1, le=60)
    recovery_window_seconds: int = Field(ge=1)
    recovery_max_attempts: int = Field(ge=1)


class SmtpSettings(BaseSettings):
    model_config = Settings.model_config
    smtp_host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.-]+$")
    smtp_port: int = Field(ge=1, le=65535)
    smtp_username: EmailStr
    smtp_password: SecretStr
    smtp_timeout_seconds: float = Field(gt=0, le=60, allow_inf_nan=False)

    @field_validator("smtp_password")
    @classmethod
    def validate_app_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value().replace(" ", "")
        if len(password) != 16 or not password.isascii() or not password.isalnum():
            raise ValueError("Configure the 16-character Gmail App Password.")
        return SecretStr(password)


class AdminBootstrapSettings(BaseSettings):
    model_config = Settings.model_config
    admin_email: EmailStr
    admin_password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("admin_password")
    @classmethod
    def reject_placeholder(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value().startswith("replace-"):
            raise ValueError("Configure a unique admin password in the private environment.")
        return value
