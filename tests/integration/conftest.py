import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.main import create_app


@pytest.fixture(scope="session")
def postgres() -> Iterator[Engine]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Export TEST_DATABASE_URL to run PostgreSQL integration tests.")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg" or not (parsed.database or "").endswith("_test"):
        pytest.fail("Tests require a dedicated PostgreSQL database ending in _test.")
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def database(postgres: Engine) -> Iterator[Engine]:
    def clear() -> None:
        with postgres.begin() as connection:
            connection.execute(text("TRUNCATE organizations, accounts"))

    clear()
    yield postgres
    clear()


@pytest.fixture
def client(database: Engine) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        database_url=database.url.render_as_string(hide_password=False),
        jwt_secret="a-test-secret-at-least-32-characters-long",
    )
    with TestClient(create_app(settings)) as client:
        yield client
