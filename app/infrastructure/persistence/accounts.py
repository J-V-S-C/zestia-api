from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.entities import (
    Account,
    AccountRole,
)
from app.application.errors import InvalidInput
from app.infrastructure.persistence.audit import record_event
from app.infrastructure.persistence.orm import (
    AccountRecord,
    AuthSessionRecord,
    RecoveryRecord,
)


class SqlAlchemyAccountRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_account(self, account_id: UUID) -> Account | None:
        record = self.session.scalar(
            select(AccountRecord)
            .where(AccountRecord.id == account_id, AccountRecord.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (
            Account(
                record.id,
                record.email,
                record.password_hash,
                record.deleted_at,
                AccountRole(record.role),
            )
            if record
            else None
        )

    def save_recovery(self, account_id: UUID, digest: str, expires_at: datetime) -> bool:
        account = self.session.scalar(
            select(AccountRecord)
            .where(AccountRecord.id == account_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if account.deleted_at is None:
            return False
        self.session.add(
            RecoveryRecord(account_id=account_id, token_hash=digest, expires_at=expires_at)
        )
        self.session.flush()
        return True

    def restore_account(self, digest: str) -> None:
        # Locate the owner first so every lifecycle operation locks account before token rows.
        candidate = self.session.get(RecoveryRecord, digest)
        if candidate is None:
            raise InvalidInput("invalid_recovery", "Recovery link is invalid or expired.")
        account = self.session.scalar(
            select(AccountRecord)
            .where(AccountRecord.id == candidate.account_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        token = self.session.scalar(
            select(RecoveryRecord)
            .where(RecoveryRecord.token_hash == digest)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = datetime.now(UTC)
        if account.deleted_at is None or token.used_at is not None or token.expires_at <= now:
            raise InvalidInput("invalid_recovery", "Recovery link is invalid or expired.")
        for recovery in self.session.scalars(
            select(RecoveryRecord).where(
                RecoveryRecord.account_id == account.id, RecoveryRecord.used_at.is_(None)
            )
        ):
            recovery.used_at = now
        self.revoke_all_sessions(account.id)
        account.deleted_at = None
        record_event(self.session, account.id, "ACCOUNT_RESTORED")
        self.session.flush()

    def save_session(self, account_id: UUID, token: str, expires_at: datetime) -> None:
        self.session.add(
            AuthSessionRecord(
                token_hash=sha256(token.encode()).hexdigest(),
                account_id=account_id,
                expires_at=expires_at,
            )
        )
        self.session.flush()

    def session_is_active(self, account_id: UUID, token: str) -> bool:
        record = self.session.get(AuthSessionRecord, sha256(token.encode()).hexdigest())
        return bool(
            record
            and record.account_id == account_id
            and record.revoked_at is None
            and record.expires_at > datetime.now(UTC)
        )

    def revoke_session(self, token: str) -> None:
        record = self.session.get(AuthSessionRecord, sha256(token.encode()).hexdigest())
        record.revoked_at = datetime.now(UTC)
        self.session.flush()

    def revoke_all_sessions(self, account_id: UUID) -> None:
        for record in self.session.scalars(
            select(AuthSessionRecord).where(
                AuthSessionRecord.account_id == account_id, AuthSessionRecord.revoked_at.is_(None)
            )
        ):
            record.revoked_at = datetime.now(UTC)
        self.session.flush()

    def find_account(self, email: str) -> Account | None:
        record = self.session.scalar(select(AccountRecord).where(AccountRecord.email == email))
        return (
            Account(
                record.id,
                record.email,
                record.password_hash,
                record.deleted_at,
                AccountRole(record.role),
            )
            if record
            else None
        )

    def save_account(self, account: Account) -> None:
        self.session.add(AccountRecord(**asdict(account)))
        self.session.flush()

    def delete_account(self, account_id: UUID) -> None:
        record = self.session.get(AccountRecord, account_id)
        record.deleted_at = datetime.now(UTC)
        self.revoke_all_sessions(account_id)
        self.session.flush()
