# Zestia backend

FastAPI + PostgreSQL 17. Organization and food CRUD are implemented; frontend, request workflows and metrics remain pending. [Requirements](../backlog.md) · [Architecture](../arch.md) · [Validation](../validation.md).

## One-time setup

From `backend/`, with Python 3.12+ and Docker Compose:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pre_commit install
```

Copy [.env.example](.env.example) to `.env` if it does not exist. Fill in every setting, using separate generated database and JWT secrets. Keep `.env` private. When reusing an existing database, preserve its credentials and Compose project name.

Initialize the database once:

```sh
docker compose up -d --wait
.venv/bin/python -m alembic upgrade head
```

Create the disposable test database once, and set TEST_DATABASE_URL in `.env` to its connection URL:

```sh
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "${POSTGRES_DB}_test"'
```

## Daily startup

Activate the environment in each new terminal:

```bash
source .venv/bin/activate
```

For fish, use `source .venv/bin/activate.fish` instead. Then start the app:

```sh
docker compose up -d --wait
python -m uvicorn app.main:create_app --factory --reload --port 8001
```

If PostgreSQL is already running, only the last command is needed. Open [Swagger](http://localhost:8001/docs) to explore the endpoints and request schemas. Health checks: `/health/live` and `/health/ready`.

## After pulling changes

If dependencies changed, rerun the two pip installation commands from setup. If new migrations were added, run:

```sh
python -m alembic upgrade head
```

Alembic updates the database schema while preserving existing data. It is needed for schema changes, rather than each startup.

## Verification

With the environment activated and PostgreSQL running:

```sh
python scripts/verify.py
```

This runs lint, formatting, dependency compatibility and known-vulnerability checks, all PostgreSQL tests with coverage, and migration checks. TEST_DATABASE_URL must point to a disposable database ending in `_test`: verification clears its data and tests migration downgrade/upgrade. Missing databases, skipped tests and failed checks fail the gate.

The vulnerability check uses [pip-audit](https://github.com/pypa/pip-audit) on an exact snapshot of installed packages, including runtime, development and transitive dependencies. Only editable project code is excluded from the package audit. Known vulnerabilities and audit errors fail verification; no findings are ignored or automatically fixed. Internet access to the advisory service is required. This scans dependency advisories; application security rules are covered separately by tests.

The installed [pre-commit hook](.pre-commit-config.yaml) runs the same script before each commit. Install it once per clone and keep `.venv` available. [GitHub Actions](.github/workflows/verify.yml) runs it on pushes and pull requests with isolated PostgreSQL fixtures and Python 3.12/3.14. GitHub execution begins after the workflow is committed and pushed.

For a quick unit-only run:

```sh
python -m pytest tests/unit -q
```

## API notes

All application paths start with `/api/v1`. Register/login under `/auth`; passwords must contain 8–128 characters. Use the returned bearer token for `/organizations` and `/foods`. Both resources support create, list, detail, update and delete. Swagger contains the complete contract.

- Each active account owns at most one active organization. All organization types can donate; owners alone can modify their records.
- Food lists accept `donor_organization_id`, `offset` and `limit` filters.
- Food quantities use Decimal kg with gram precision. Creation/editing accept expiration dates from today onward in America/Sao_Paulo.
- `DELETE /auth/me` closes the authenticated account and archives its unused organization atomically. Closed accounts cannot log in or use existing tokens; their email stays reserved. Closure returns 409 while the organization has food or requests.
- Organization deletion sets `deleted_at`, hides it from normal reads, and permits a replacement organization. Account/organization rows are retained; there is no automatic purge or restore endpoint.
- Approved quantities limit reductions; any associated request blocks food deletion. Referenced organizations cannot be deleted.
- Errors use `{"error":{"code":"...","message":"..."}}`, with HTTP 401/403/404/409/422/503 as appropriate.

Request records currently support food integrity checks; request creation, approval/rejection and history endpoints remain E03. Detailed rules belong in the [backlog](../backlog.md).
