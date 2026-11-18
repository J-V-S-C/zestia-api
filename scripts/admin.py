"""Bootstrap/revoke an admin using private ADMIN_EMAIL and ADMIN_PASSWORD settings."""

import argparse
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.application.entities import AccountRole
from app.config import AdminBootstrapSettings, Settings
from app.infrastructure.models import AccountRecord, LifecycleEventRecord
from app.infrastructure.security import Argon2PasswordHasher


def provision_admin(
    session: Session, settings: AdminBootstrapSettings, *, revoke: bool = False
) -> None:
    email = str(settings.admin_email).strip().casefold()
    password = settings.admin_password.get_secret_value()
    hasher = Argon2PasswordHasher()
    account = session.scalar(
        select(AccountRecord).where(AccountRecord.email == email).with_for_update()
    )
    if account is None:
        if revoke:
            raise ValueError("Admin account does not exist.")
        account = AccountRecord(
            id=uuid4(), email=email, password_hash=hasher.hash(password), role=AccountRole.USER
        )
        session.add(account)
        session.flush()
    elif account.deleted_at is not None:
        raise ValueError("Cannot provision a closed account. Use the recovery flow first.")
    elif not hasher.verify(password, account.password_hash):
        raise ValueError(
            "Configured password does not match the existing account; no changes made."
        )
    desired_role = AccountRole.USER if revoke else AccountRole.ADMIN
    if account.role == desired_role:
        return
    account.role = desired_role
    session.add(
        LifecycleEventRecord(
            id=uuid4(),
            account_id=account.id,
            action="ADMIN_REVOKED" if revoke else "ADMIN_GRANTED",
            reason="Local operator provisioning from private environment",
        )
    )
    session.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revoke", action="store_true")
    arguments = parser.parse_args()
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
                provision_admin(session, bootstrap, revoke=arguments.revoke)
            except ValueError as error:
                raise SystemExit(str(error)) from None
        print("Admin role configured.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
