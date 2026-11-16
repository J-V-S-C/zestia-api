# ReAlimenta backend — Epic 1

Organization CRUD with FastAPI, PostgreSQL 17 and SQLAlchemy 2.0. Requirements: [E01 / RF-01 / RN-01–02](../backlog.md). SUPERMARKET, NGO and COMMUNITY_KITCHEN classify institutions; they are not permission roles.

## Run locally

From `backend/`, with Python 3.12+ and Docker Compose:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Copy `.env.example` to `.env` if missing. Set JWT_SECRET to a generated secret of at least 32 characters: `python -c 'import secrets; print(secrets.token_urlsafe(48))'`. The example placeholder is rejected; this workspace already has an ignored secret configured.

```bash
docker compose -p realimenta up -d --wait
alembic upgrade head
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
```

An existing PostgreSQL container was reused with new databases `realimenta_e01` and `realimenta_e01_test`; earlier prototype data was preserved. When reusing a volume, create the database named in DATABASE_URL if it does not exist. Existing volume credentials remain unchanged. Do not bind two containers to the same port.

[Swagger](http://localhost:8001/docs) provides request schemas; `/openapi.json` is the executable contract. Health checks: `/health/live` and `/health/ready`. Startup never creates tables.

## API

Paths use `/api/v1`:

| Method | Path | Behavior |
|---|---|---|
| POST | `/auth/register` | Account with email and 12–128 character password; 201. |
| POST | `/auth/login` | JSON email/password → access_token, token_type, expires_in. |
| GET | `/auth/me` | Current account; never password hashes. |
| POST | `/organizations` | Create own organization; 201 and Location header. |
| GET | `/organizations` | List all; offset=0, limit=50 (max 100). |
| GET | `/organizations/{organization_id}` | Read one. |
| PUT | `/organizations/{organization_id}` | Owner replaces name/type/location. |
| DELETE | `/organizations/{organization_id}` | Owner deletes an unused organization; 204. |

Organization endpoints require `Authorization: Bearer <access_token>`. Each account owns at most one organization. Authenticated users browse all organizations; only owners modify/delete. Deleting an organization preserves its account, which may create a replacement.

```json
{"name":"Fictional Kitchen","type":"COMMUNITY_KITCHEN","location":"Porto Alegre"}
```

Name/location are trimmed, required and limited to 160/240 characters. Client-supplied ownership fields are rejected. SQL pagination is ordered by name/id. Argon2 protects passwords; JWTs expire after 60 minutes by default.

Errors: `{"error":{"code":"...","message":"..."}}`. HTTP 401 authentication, 403 ownership, 404 missing resource, 409 conflict, 422 validation, 503 database unavailable. Validation errors omit submitted input values.

RN-02 translates PostgreSQL foreign-key deletion restrictions into 409. E02/E03 must reference organizations with ON DELETE RESTRICT. Their tables are not implemented here; integration tests use a real referencing record to verify the restriction.

## Configuration and verification

`.env`: DATABASE_URL (postgresql+psycopg), JWT_SECRET (random, ≥32 characters), ACCESS_TOKEN_MINUTES (60), CORS_ORIGINS (JSON list; default localhost:3000). POSTGRES_USER/PASSWORD/DB initialize Compose; they must agree with DATABASE_URL. Keep `.env` out of Git.

```bash
python -m pytest tests/unit -v
ruff check app tests migrations
ruff format --check app tests migrations
```

Create a separate test database once, then run:

```bash
docker compose -p realimenta exec -T postgres createdb -U realimenta realimenta_e01_test
TEST_DATABASE_URL=postgresql+psycopg://realimenta:realimenta@localhost:5432/realimenta_e01_test python -m pytest --cov=app --cov-branch --cov-report=term-missing -q
```

Tests migrate and clear that database. Without the shell variable, integration tests skip. Coverage includes types, invalid inputs, persisted CRUD, ownership, missing resources, concurrent creation, dependency-protected deletion, passwords and invalid tokens.

For schema changes, generate/review an Alembic revision, then run `alembic upgrade head` and `alembic check`. Layers: [arch.md](../arch.md). Frontend, E02–E04, account recovery/verification and token refresh/revocation remain pending.

Service unit tests live in `tests/unit` and mock only external ports. HTTP integration/E2E tests live in `tests/integration`: TestClient drives the real ASGI app, real hashing/JWT, migrations and PostgreSQL (no service/repository substitutes). They exercise the API end to end in process, rather than through a deployed server. Run `pytest -m e2e` with TEST_DATABASE_URL to select them. Coverage is collected across both suites; unit-only runs do not measure HTTP/persistence coverage.
