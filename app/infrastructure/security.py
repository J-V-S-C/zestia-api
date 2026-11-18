from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

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
        self.issuer = settings.jwt_issuer
        self.audience = settings.jwt_audience

    def issue(self, account_id: UUID) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": str(account_id),
                "jti": str(uuid4()),
                "iat": now,
                "exp": now + timedelta(minutes=self.minutes),
                "iss": self.issuer,
                "aud": self.audience,
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
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["sub", "iat", "exp", "iss", "aud", "jti"]},
            )
            return UUID(claims["sub"])
        except (jwt.InvalidTokenError, TypeError, ValueError) as error:
            raise Unauthenticated("invalid_token", "A valid access token is required.") from error
