from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Protocol
from uuid import UUID

from app.application.entities import Account
from app.application.errors import InvalidInput


class RecoveryDelivery(Protocol):
    def __call__(self, email: str, token: str) -> None: ...


class RecoveryRepository(Protocol):
    def find_account(self, email: str) -> Account | None: ...
    def save_recovery(self, account_id: UUID, digest: str, expires_at: datetime) -> bool: ...
    def restore_account(self, digest: str) -> None: ...


class RecoveryService:
    def __init__(self, repository: RecoveryRepository) -> None:
        self.repository = repository

    def request(self, email: str, lifetime_minutes: int) -> str | None:
        account = self.repository.find_account(email.strip().casefold())
        if account is None or account.deleted_at is None:
            return None
        token = token_urlsafe(48)
        saved = self.repository.save_recovery(
            account.id,
            sha256(token.encode()).hexdigest(),
            datetime.now(UTC) + timedelta(minutes=lifetime_minutes),
        )
        return token if saved else None

    def restore(self, token: str) -> None:
        if not token or len(token) > 256:
            raise InvalidInput("invalid_recovery", "Recovery link is invalid or expired.")
        self.repository.restore_account(sha256(token.encode()).hexdigest())
