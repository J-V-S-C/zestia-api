"""Synchronize the single admin with private ADMIN_EMAIL and ADMIN_PASSWORD settings."""

import argparse
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import create_engine, func, or_, select
from sqlalchemy.orm import Session

from app.application.entities import AccountRole
from app.config import AdminBootstrapSettings, Settings
from app.infrastructure.persistence.accounts import SqlAlchemyAccountRepository
from app.infrastructure.persistence.orm import AccountRecord, LifecycleEventRecord, RecoveryRecord
from app.infrastructure.security.passwords import Argon2PasswordHasher


def provision_admin(session: Session, settings: AdminBootstrapSettings) -> None:
    email = str(settings.admin_email).strip().casefold()
    password = settings.admin_password.get_secret_value()
    hasher = Argon2PasswordHasher()
    # Serialize even the first bootstrap, when no admin row exists to lock yet.
    session.execute(select(func.pg_advisory_xact_lock(func.hashtext("zestia.admin.bootstrap"))))
    accounts = list(
        session.scalars(
            select(AccountRecord)
            .where(or_(AccountRecord.role == AccountRole.ADMIN, AccountRecord.email == email))
            .order_by(AccountRecord.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    account = next((record for record in accounts if record.email == email), None)
    if account is not None and account.deleted_at is not None:
        raise ValueError("Cannot provision a closed account. Use the recovery flow first.")
    password_changed = account is not None and not hasher.verify(password, account.password_hash)
    if password_changed and account.role != AccountRole.ADMIN:
        raise ValueError(
            "Configured password does not match the existing user account; no changes made."
        )

    now = datetime.now(UTC)
    repository = SqlAlchemyAccountRepository(session)
    for previous in accounts:
        if previous.role == AccountRole.ADMIN and previous is not account:
            previous.role = AccountRole.USER
            previous.deleted_at = previous.deleted_at or now
            repository.revoke_all_sessions(previous.id)
            for recovery in session.scalars(
                select(RecoveryRecord).where(
                    RecoveryRecord.account_id == previous.id, RecoveryRecord.used_at.is_(None)
                )
            ):
                recovery.used_at = now
            session.add(
                LifecycleEventRecord(
                    id=uuid4(),
                    account_id=previous.id,
                    action="ADMIN_RETIRED",
                    reason="Account closed by configured single-admin replacement",
                )
            )
    # Release the unique admin slot before granting it to the configured identity.
    session.flush()

    if account is None:
        account = AccountRecord(
            id=uuid4(), email=email, password_hash=hasher.hash(password), role=AccountRole.USER
        )
        session.add(account)
        session.flush()
    if password_changed:
        account.password_hash = hasher.hash(password)
        repository.revoke_all_sessions(account.id)
        session.add(
            LifecycleEventRecord(
                id=uuid4(),
                account_id=account.id,
                action="ADMIN_PASSWORD_ROTATED",
                reason="Password synchronized from private bootstrap configuration",
            )
        )
    if account.role == AccountRole.ADMIN:
        session.flush()
        return
    account.role = AccountRole.ADMIN
    session.add(
        LifecycleEventRecord(
            id=uuid4(),
            account_id=account.id,
            action="ADMIN_GRANTED",
            reason="Local operator provisioning from private environment",
        )
    )
    session.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        bootstrap = AdminBootstrapSettings()
        settings = Settings()
    except ValidationError:
        raise SystemExit(
            "Configure valid application settings, ADMIN_EMAIL and ADMIN_PASSWORD "
            "in the private environment."
        ) from None
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as session, session.begin():
            try:
                provision_admin(session, bootstrap)
            except ValueError as error:
                raise SystemExit(str(error)) from None
        print("Admin role configured.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
