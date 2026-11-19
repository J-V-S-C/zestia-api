# Zestia backend

FastAPI + PostgreSQL 17. Organization/food CRUD, request workflows and metrics are implemented. Live recovery email delivery awaits provider integration. [Requirements](../backlog.md) · [Architecture](../arch.md) · [Validation](../validation.md).

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

To seed the initial administrator, follow [Admin seed](#admin-seed). This is a one-time setup step, not part of daily startup.

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

All application paths start with `/api/v1`. Register/login under `/auth`; passwords must contain 8–128 characters. Use the returned bearer token for `/organizations`, `/foods` and `/requests`. Organizations and foods support create, list, detail, update and delete. Swagger contains the complete contract.

- Each active account owns at most one active organization. All organization types can donate; owners alone can modify their records.
- Food lists accept `donor_organization_id`, `offset` and `limit` filters.
- Food quantities use Decimal kg with gram precision. Creation/editing accept expiration dates from today onward in America/Sao_Paulo.
- `DELETE /auth/me` closes the authenticated account and archives its unused organization atomically. Closed accounts cannot log in or use existing tokens; their email stays reserved. Closure returns 409 while the organization has food or requests.
- Organization deletion sets `deleted_at`, hides it from normal reads, and permits a replacement organization. Account/organization rows are retained; restoration is described below and there is no automatic purge.
- Approved quantities limit reductions; any associated request blocks food deletion. Referenced organizations cannot be deleted.
- Errors use `{"error":{"code":"...","message":"..."}}`, with HTTP 401/403/404/409/422/503 as appropriate.

### Requests

| Method | Path (under `/api/v1`) | Purpose |
|---|---|---|
| POST | `/requests` | Request `{ "food_id": "<UUID>", "quantity_kg": "1.125" }`; returns 201 and a Location header. |
| GET | `/requests` | List the current organization's sent and received requests. |
| GET | `/requests/{id}` | View a request as its donor or recipient. |
| POST | `/requests/{id}/approve` | Donor approves a pending request. |
| POST | `/requests/{id}/reject` | Donor rejects a pending request. |

Creation derives the recipient from the authenticated owner. Responses include food, donor and recipient IDs, Decimal kg, status and a timezone-aware creation timestamp. History accepts `status`, `donor_organization_id`, `recipient_organization_id`, `offset` and `limit`; filters apply before pagination and cannot expose another organization's requests. Accounts without an organization receive an empty list.

Pending requests do not reserve food. Creation and approval validate the approved balance under a food-row lock shared with food edits/deletion; approval also rechecks expiration. Only PENDING requests can be processed, and only their donor can process them. VERIFIED status is required for request creation and donor approval. Other verification statuses retain history access and may reject pending requests, including expired food. Detailed rules belong in the [backlog](../backlog.md).

### Metrics

| Method | Path (under `/api/v1`) | Purpose |
|---|---|---|
| GET | `/metrics` | Active organization count, registered kg and request totals/quantities/status counts. |
| GET | `/metrics/organizations` | Organization breakdown separating requests for its donations from requests it made. |

Both require an active authenticated session and accept `organization_id` and `status` (PENDING/APPROVED/REJECTED). Aggregates are platform-visible; individual request history remains participant-only. No account emails, credentials or individual request records are returned.

The summary's `requests` contains `total_requests`, `requested_food_kg`, `approved_food_kg`, `pending_requests`, `approved_requests` and `rejected_requests`. An organization filter restricts registered food to that donor and includes each request involving it as donor or recipient once. The breakdown uses `donation_requests` for requests against its food and `recipient_requests` for requests it made. Sum each role separately across organizations; adding both roles would count the same requests twice.

Status filters affect request figures only; organization counts and registered kg stay unchanged. Existing listings include expired food for historical accuracy. Archived organizations are excluded from organization counts/breakdown; persisted food/request history is retained. Unknown organization filters return zero totals/empty groups. Breakdown pagination uses `offset` and `limit` (1–100), after filtering, ordered by name/ID; it does not change summary totals. Each response uses one SQL snapshot. Quantities use Decimal kg with three decimal places, including zero; approved kg imply no delivery, consumption or waste reduction.

## Account lifecycle and organization review

| Method | Path (under `/api/v1`) | Purpose |
|---|---|---|
| POST | `/auth/logout` | Revoke the current bearer session; other sessions stay active. |
| GET | `/auth/me/organizations/archived` | List the current owner's archived organizations, with pagination. |
| POST | `/organizations/{id}/restore` | Restore an owned archive; returns 409 if another organization is active. |
| POST | `/auth/recovery/request` | Request recovery instructions; live delivery is deferred and currently returns 503. |
| POST | `/auth/recovery/confirm` | Consume a valid recovery token and restore the account; fresh login is required. |
| POST | `/organizations/{id}/verification` | Owner submits `{ "evidence": "..." }` for manual review. |
| GET | `/organizations/{id}/verification` | Authorized admin reads the submitted evidence. |
| POST | `/organizations/{id}/verification/review` | Admin submits `{ "status": "VERIFIED", "reason": "..." }`. |

New and existing organizations start PENDING after the migration. Only VERIFIED organizations can publish/edit food, create requests or approve donations; owners can still delete unused listings and reject pending requests. Owners cannot self-verify; the ADMIN account role is stored in the database. Admins cannot approve their own organizations. Reviewed identity/type changes require new evidence and review. Suspension prevents participation and cannot be cleared by owner edits.

### Admin seed

[`scripts/admin.py`](scripts/admin.py) synchronizes the single admin with the configured credentials. It can safely be rerun; it does not create sample organizations or food.

After applying migrations, set ADMIN_EMAIL and ADMIN_PASSWORD privately in `.env` or the environment, then run from `backend/`:

```sh
.venv/bin/python scripts/admin.py
```

Passwords are stored as Argon2 hashes. `/auth/me` reports the stored role; public signup always creates USER accounts. Keep credentials out of Git and command-line arguments.

The API requires ADMIN_EMAIL at startup and reserves that email from public signup, even before bootstrap runs. Matching ignores letter case; signup returns 409 regardless of the supplied password. ADMIN_PASSWORD is only needed by the bootstrap script. Using that password with another email never grants privileges; authorization uses the stored role.

Bootstrap enforces one admin after a successful transaction:

| Input | Result |
|---|---|
| Same email/password | Keeps the same account, password hash and sessions; no duplicate grant event. |
| Same admin email, different password | Updates its hash and revokes all sessions; fresh login with the configured password is required. |
| Different email | Creates/grants the configured admin and soft-deletes the previous admin account, removes its role, revokes every session and invalidates pending recovery links. |
| Existing ordinary user email | Promotes only when the configured password matches; otherwise rejects without retiring the current admin. |
| Closed account, even with matching password | Rejects; bootstrap cannot bypass recovery. |

Old admin rows remain as deleted USER records to preserve audit history and organization/food/request references; they cannot log in or use old tokens. This administrative retirement preserves linked records even when ordinary account closure would be blocked by those links. Replacement, password changes, session/recovery revocation and audit events commit together. Failure rolls everything back, leaving the previous admin usable. The old `--revoke` option is removed; changing the configured identity and running bootstrap performs replacement.

A PostgreSQL unique index prevents a second ADMIN row, and a transaction advisory lock serializes bootstrap runs, including first creation. The new migration stops if multiple legacy admins exist: run the updated bootstrap with the intended credentials to consolidate them, then retry `python -m alembic upgrade head`. Migration never chooses an admin arbitrarily. Changing configuration alone does not update stored credentials: run bootstrap, then restart the API so signup reserves the current ADMIN_EMAIL.

Admins must check identity, representation and supporting evidence; informal kitchens can submit alternative evidence. No registry or document provider is integrated.

### Recovery delivery

Recovery settings are required when using recovery endpoints: RECOVERY_TOKEN_MINUTES, RECOVERY_WINDOW_SECONDS and RECOVERY_MAX_ATTEMPTS. Recovery limits are persisted per IP and per requested email. Only token hashes are stored; tokens expire, are single-use and are invalidated together on restoration. Restoration never reactivates old sessions or silently restores organizations. The delivery port is injected into `create_app`; tests use an in-memory fixture. No real messages are sent, and the default app explicitly reports recovery delivery unavailable. All external integrations—including email and Supabase—remain the final phase.

The session migration requires existing clients to log in again. Frontends must call logout before clearing their local token. The frontend itself remains pending.
