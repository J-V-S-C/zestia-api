from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).parents[1] / ".env", extra="ignore")
    database_url: str
    jwt_secret: SecretStr
    jwt_issuer: str = Field(min_length=1)
    jwt_audience: str = Field(min_length=1)
    access_token_minutes: int = Field(ge=1, le=1440)
    cors_origins: list[str]

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
