"""Checks run before commits and in CI:

- Git whitespace errors and installed dependency compatibility.
- Known dependency vulnerabilities (pip-audit).
- Pre-commit configuration, Ruff lint and formatting.
- Database migrations and agreement between schema and models.
- All unit/integration tests, with coverage; skipped tests fail the gate.
- Full migration downgrade and upgrade on the disposable test database.

Use --pre-commit for unit tests and static checks without a database.
Full verification (CI) requires TEST_DATABASE_URL ending in _test. Tests clear
its records and migration checks drop/rebuild its tables. The name check helps
prevent accidentally running these destructive checks against application data;
it does not provide backups or secure the database. The application can use
Supabase independently, configured through DATABASE_URL.
"""

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
        raise ValueError("Set TEST_DATABASE_URL in the environment before full verification.")
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--pre-commit", action="store_true", help="Run checks and unit tests without PostgreSQL."
    )
    mode.add_argument("--env-file", type=Path, help="Explicit configuration for full verification.")
    arguments = parser.parse_args()
    if arguments.env_file is not None:
        load_dotenv(arguments.env_file)
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    try:
        database_url = None if arguments.pre_commit else require_test_database()
        run(sys.executable, "scripts/scan_secrets.py")
        run("git", "diff", "--check")
        run("git", "diff", "--cached", "--check")
        run(sys.executable, "-m", "pip", "check")
        with tempfile.TemporaryDirectory(prefix="zestia-audit-") as directory:
            # Build an exact snapshot including transitive dependencies. Editable application
            # code has no package advisory entry and is checked by lint and tests instead.
            snapshot = Path(directory) / "requirements.txt"
            snapshot.write_text(
                subprocess.check_output(
                    [sys.executable, "-m", "pip", "list", "--format=freeze", "--exclude-editable"],
                    cwd=ROOT,
                    text=True,
                )
            )
            run(
                sys.executable,
                "-m",
                "pip_audit",
                "--strict",
                "--no-deps",
                "--disable-pip",
                "-r",
                str(snapshot),
            )
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
        if arguments.pre_commit:
            with tempfile.TemporaryDirectory(prefix="zestia-unit-verification-") as directory:
                report = Path(directory) / "pytest.xml"
                run(
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/unit",
                    "--strict-config",
                    "--strict-markers",
                    f"--junitxml={report}",
                    "-q",
                )
                require_no_skipped_tests(report)
            print("Pre-commit checks passed. Integration tests and migrations run in CI.")
            return 0
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
