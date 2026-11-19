from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.config import AdminBootstrapSettings
from app.infrastructure.persistence.orm import AccountRecord
from app.infrastructure.security.passwords import Argon2PasswordHasher
from scripts.admin import provision_admin

pytestmark = pytest.mark.integration


def test_legacy_admins_must_be_consolidated_before_singleton_migration(database):
    config = Config("alembic.ini")
    config.attributes["database_url"] = database.url.render_as_string(hide_password=False)
    command.downgrade(config, "b82c61394e0f")
    try:
        password_hash = Argon2PasswordHasher().hash("legacy-test-password")
        with Session(database) as session, session.begin():
            for email in ("legacy-one@example.com", "legacy-two@example.com"):
                session.add(
                    AccountRecord(
                        id=uuid4(), email=email, password_hash=password_hash, role="ADMIN"
                    )
                )
        with pytest.raises(DBAPIError, match="Multiple legacy admins exist"):
            command.upgrade(config, "head")
        with database.connect() as connection:
            assert (
                connection.scalar(text("SELECT count(*) FROM accounts WHERE role = 'ADMIN'")) == 2
            )
        settings = AdminBootstrapSettings(
            _env_file=None,
            admin_email="legacy-two@example.com",
            admin_password="legacy-test-password",
        )
        with Session(database) as session, session.begin():
            provision_admin(session, settings)
        command.upgrade(config, "head")
        command.check(config)
        with Session(database) as session:
            admin = session.scalar(select(AccountRecord).where(AccountRecord.role == "ADMIN"))
            assert admin.email == "legacy-two@example.com"
            old = session.scalar(
                select(AccountRecord).where(AccountRecord.email == "legacy-one@example.com")
            )
            assert old.role == "USER"
            assert old.deleted_at is not None
            assert session.scalar(text("SELECT count(*) FROM accounts WHERE role = 'ADMIN'")) == 1
    finally:
        # Restore the disposable test schema even when an assertion fails.
        with database.begin() as connection:
            connection.execute(text("UPDATE accounts SET role = 'USER'"))
        command.upgrade(config, "head")
