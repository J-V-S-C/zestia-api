"""Run the same checks before commits and in CI, using only a dedicated test database."""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ROOT = Path(__file__).resolve().parents[1]


def require_test_database() -> str:
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        raise ValueError("Set TEST_DATABASE_URL in the environment or .env before verification.")
    try:
        url = make_url(value)
    except ArgumentError as error:
        raise ValueError("TEST_DATABASE_URL must be a valid PostgreSQL URL.") from error
    if url.drivername != "postgresql+psycopg" or not (url.database or "").endswith("_test"):
        raise ValueError(
            "Verification requires a dedicated postgresql+psycopg database ending in _test."
        )
    return value


def run(*arguments: str) -> None:
    print(f"Running: {' '.join(arguments)}", flush=True)
    subprocess.run(arguments, cwd=ROOT, check=True)


def require_no_skipped_tests(report: Path) -> None:
    if ElementTree.parse(report).findall(".//testcase/skipped"):
        raise ValueError("Verification failed: tests were skipped. All tests must run.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    arguments = parser.parse_args()
    load_dotenv(arguments.env_file)
    try:
        database_url = require_test_database()
        run("git", "diff", "--check")
        run("git", "diff", "--cached", "--check")
        run(sys.executable, "-m", "pip", "check")
        run(sys.executable, "-m", "pre_commit", "validate-config")
        run(sys.executable, "-m", "ruff", "check", "app", "tests", "migrations", "scripts")
        run(
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "app",
            "tests",
            "migrations",
            "scripts",
        )
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["database_url"] = database_url
        print("Migrating the test database and checking schema consistency.", flush=True)
        command.upgrade(config, "head")
        command.check(config)
        with tempfile.TemporaryDirectory(prefix="zestia-verification-") as directory:
            report = Path(directory) / "pytest.xml"
            run(
                sys.executable,
                "-m",
                "pytest",
                "--strict-config",
                "--strict-markers",
                "--cov=app",
                "--cov-branch",
                "--cov-report=term-missing",
                f"--junitxml={report}",
                "-q",
            )
            require_no_skipped_tests(report)
        print(
            "Checking migration downgrade to base and upgrade to head on the test database.",
            flush=True,
        )
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        command.check(config)
    except (ValueError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print("All verification checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
