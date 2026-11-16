from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.application.errors import Unauthenticated
from app.config import Settings


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self.hasher = PasswordHash.recommended()
        self.dummy_hash = self.hasher.hash("unused-dummy-password")

    def hash(self, password: str) -> str:
        return self.hasher.hash(password)

    def verify(self, password: str, password_hash: str | None) -> bool:
        return self.hasher.verify(password, password_hash or self.dummy_hash)


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self.secret = settings.jwt_secret.get_secret_value()
        self.minutes = settings.access_token_minutes

    def issue(self, account_id: UUID) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": str(account_id),
                "iat": now,
                "exp": now + timedelta(minutes=self.minutes),
                "iss": "realimenta",
                "aud": "realimenta-api",
            },
            self.secret,
            algorithm="HS256",
        )

    def subject(self, token: str) -> UUID:
        try:
            claims = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                issuer="realimenta",
                audience="realimenta-api",
                options={"require": ["sub", "iat", "exp", "iss", "aud"]},
            )
            return UUID(claims["sub"])
        except (jwt.InvalidTokenError, TypeError, ValueError) as error:
            raise Unauthenticated("invalid_token", "A valid access token is required.") from error
