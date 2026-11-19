# Zestia backend

## Ficha CitizenTech

| Campo | Definição |
|---|---|
| CitizenTech | Zestia — conexão entre organizações para doações de alimentos |
| Cidade e bairro | Porto Alegre/RS; escopo municipal, bairro-piloto ainda não definido e sem implantação real declarada |
| Cidadão beneficiado | Pessoas atendidas por cozinhas comunitárias e organizações receptoras |
| Problema | Dificuldade de compatibilizar alimentos disponíveis com necessidades e capacidade de recebimento das organizações |
| Funcionamento | Organizações publicam alimentos, solicitam quantidades, aprovam/rejeitam pedidos e consultam indicadores |
| Partes | API Python armazena e valida dados; PostgreSQL persiste registros; programa de análise gera apoio à decisão; SMTP entrega códigos de recuperação quando configurado |
| Repositório | [zestia-api](https://github.com/J-V-S-C/zestia-api) |
| Indicador | Kg solicitados/aprovados e pedidos por status. Aprovação não comprova entrega, consumo ou redução de desperdício |
| ODS relacionados | ODS 2 — Fome Zero; ODS 12 — Consumo e Produção Responsáveis. Contribuições propostas, sem impacto real medido |

O problema local permanece uma hipótese: não há entrevistas documentadas neste repositório. Dados de demonstração são fictícios, não evidência de doações ou de impacto na cidade.

## Computational Thinking with Python

Quickstart sem banco, credenciais ou acesso à rede após instalar as dependências:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python scripts/demo.py
```

O programa lê [data/demo.json](data/demo.json), processa quantidades/status/validade com Decimal e produz [o relatório reproduzível](data/demo-report.json). São 33 kg cadastrados, 27 kg solicitados e 12 kg aprovados. O feijão vence antes do arroz; dois pedidos de arroz somam 10 kg para um saldo de 8 kg, exigindo decisão do doador e nova validação transacional. O pedido de pão vencido é sinalizado. [Demonstração e interpretação](docs/PYTHON.md).

Equipe: João Victor Sant'Ana Cortabitart (RM 573865), João Victor Barbon Naymayer (RM 574025) e João Vitor Dutra de Freitas (RM 573678). [Integrantes](INTEGRANTES.md) · [Uso de IA](AI.md) · [Registro de prompts](PROMPTS.md) · [Entrega](docs/SUBMISSION.md).

[Agreed decisions](DECISIONS.md)

OCI/Caddy deployment and owner configuration: [production runbook](deploy/README.md). The workflow is prepared; production is not yet activated.

FastAPI + PostgreSQL 17. Organization/food CRUD, request workflows, metrics and a Gmail SMTP recovery adapter are implemented. Live delivery still requires private sender configuration and an operator check. [Decisions and rules](DECISIONS.md) · [Python demonstration](docs/PYTHON.md) · [Validation](docs/VALIDATION.md).

## One-time setup

Code responsibilities: `application/entities.py` defines domain entities; `application/ports/` defines contracts; `application/services/` implements use cases; `application/query_results.py` defines report results. Infrastructure is grouped into `http/`, `persistence/`, `security/` and `email/`. HTTP DTOs live in `http/dtos.py`; SQLAlchemy mappings live in `persistence/orm.py`. `http/providers.py` wires dependencies and request transactions; `main.py` assembles the application. Routes are grouped by resource.

From `backend/`, with Python 3.12+, Docker Compose and Go (for the pinned secret scanner):

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps -e .
GOBIN="$PWD/.venv/bin" go install github.com/zricethezav/gitleaks/v8@v8.30.1
.venv/bin/python -m pre_commit install
```

Copy [.env.example](.env.example) to `.env` if it does not exist. Fill in every setting, using separate generated database and JWT secrets. Keep `.env` private. When reusing an existing database, preserve its credentials and Compose project name.

Initialize the database once:

```sh
docker compose up -d --wait
.venv/bin/python -m alembic upgrade head
```

For optional manual integration verification, create a disposable test database and export TEST_DATABASE_URL. This is not required for commits:

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

The shared gate requires Go-installed [Gitleaks](https://github.com/gitleaks/gitleaks) v8.30.1 as shown above. It scans tracked/untracked source and staged contents offline, with redacted diagnostics; scanner failure or findings fail verification. GitGuardian remains a separate required PR check because detectors differ. The only scanner exception is the exact public JWT value at the disposable CI fixture path; tests prove other credentials there are still rejected. Tracked private `.env` paths are rejected without opening them. The public `.env.example` template is scanned, including its staged contents; completed private files remain off limits. No test directory is excluded, and no secret detector is disabled.

With the environment activated and PostgreSQL running:

```sh
python scripts/verify.py
```

This runs lint, formatting, dependency compatibility and known-vulnerability checks, all PostgreSQL tests with coverage, and migration checks. TEST_DATABASE_URL must point to a disposable database ending in `_test`: verification clears its data and tests migration downgrade/upgrade. Missing databases, skipped tests and failed checks fail the gate.

The vulnerability check uses [pip-audit](https://github.com/pypa/pip-audit) on an exact snapshot of installed packages, including runtime, development and transitive dependencies. Only editable project code is excluded from the package audit. Known vulnerabilities and audit errors fail verification; no findings are ignored or automatically fixed. Internet access to the advisory service is required. This scans dependency advisories; application security rules are covered separately by tests.

The installed [pre-commit hook](.pre-commit-config.yaml) runs `python scripts/verify.py --pre-commit`: secret scanning, lint/format, dependency checks and unit tests. It requires no PostgreSQL or TEST_DATABASE_URL and does not load `.env`. Integration tests, full coverage and migrations run in CI using the full verification mode. Install it once per clone and keep `.venv` available. [GitHub Actions](.github/workflows/verify.yml) runs it on pushes and pull requests with isolated PostgreSQL fixtures and Python 3.12/3.14. GitHub execution begins after the workflow is committed and pushed.

For a quick unit-only run:

```sh
python -m pytest tests/unit -q
```

## API notes

All application paths start with `/api/v1`. Register/login under `/auth`; passwords must contain 8–128 characters. Use the returned bearer token for `/organizations`, `/foods` and `/requests`. Organizations and foods support create, list, detail, update and delete. Swagger contains the complete contract.

- Each active account owns at most one active organization. All organization types can donate; owners alone can modify their records.
- `GET /auth/me/organization` returns the logged-in account's active organization, including its ID and verification status. It derives ownership from the bearer session; no account/organization ID is required. Returns 404 when none exists or only archived organizations exist, and 401 without an active session. Owners can read their organization in every verification state.
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

Pending requests do not reserve food. Creation and approval validate the approved balance under a food-row lock shared with food edits/deletion; approval also rechecks expiration. Only PENDING requests can be processed, and only their donor can process them. VERIFIED status is required for request creation and donor approval. Other verification statuses retain history access and may reject pending requests, including expired food. [Agreed decisions and rules](DECISIONS.md).

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
| POST | `/auth/recovery/request` | Request recovery instructions; returns 503 when delivery is disabled, otherwise generic 202. |
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

Gmail SMTP was selected for this MVP; a custom domain is unnecessary. Use a dedicated Gmail sender, enable 2-Step Verification, and create an [App Password](https://support.google.com/accounts/answer/185833). Some restricted Google accounts do not support App Passwords. The owner manages all credentials privately; the assistant never reads or modifies environment files.

Set `RECOVERY_EMAIL_ENABLED` to true to enable the adapter. Supply `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME` (the sender address), `SMTP_PASSWORD` (the App Password) and `SMTP_TIMEOUT_SECONDS` (positive, at most 60). Gmail's documented STARTTLS endpoint is `smtp.gmail.com` on port `587`: [Google SMTP documentation](https://developers.google.com/workspace/gmail/imap/imap-smtp). The sender is the authenticated account; the App Password's display spaces are normalized. No plaintext SMTP authentication or TLS downgrade is supported.

Also configure `RECOVERY_TOKEN_MINUTES`, `RECOVERY_WINDOW_SECONDS` and `RECOVERY_MAX_ATTEMPTS`. Enabling email with missing/invalid SMTP or recovery settings fails startup. Email delivery defaults to disabled; explicit injected delivery adapters remain supported for tests. Recovery limits persist per IP/requested email; only token hashes are stored. Tokens expire, are single-use and are invalidated together on restoration. Restoration requires fresh login and does not silently restore organizations.

Delivery runs after the token transaction commits. The email contains a recovery code; submit it to `/auth/recovery/confirm` using its `token` field. The generic 202 response acknowledges the request, not successful delivery. SMTP/network errors produce a generic log entry without exception content, addresses, credentials or raw codes. There is no durable retry queue; after a delivery failure the user can request a new code within the configured limits. Inbox placement is not guaranteed. Automated tests use fake SMTP only; no real email or operator credentials are needed. Live account setup and a controlled operator delivery check remain necessary before RF-10 acceptance.

The session migration requires existing clients to log in again. Frontends must call logout before clearing their local token. The frontend itself remains pending.
