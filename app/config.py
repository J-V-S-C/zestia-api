from pathlib import Path

from pydantic import EmailStr, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).parents[1] / ".env", extra="ignore")
    database_url: str
    jwt_secret: SecretStr
    jwt_issuer: str = Field(min_length=1)
    jwt_audience: str = Field(min_length=1)
    access_token_minutes: int = Field(ge=1, le=1440)
    cors_origins: list[str]
    admin_email: EmailStr

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
