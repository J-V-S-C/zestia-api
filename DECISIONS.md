# Zestia — decision record

Updated: 2026-11-19. Records agreed choices; implementation and acceptance are separate statuses.

| Area | Agreed decision | Reason |
|---|---|---|
| Scope | Finish the backend; frontend is outside this batch. | Keep the current work focused. |
| External API task | The Web Development checklist requires the frontend to consume the backend API. | It does not require inventing an additional third-party backend service. |
| Stack | Python/FastAPI, PostgreSQL 17, SQLAlchemy/Psycopg and Alembic. | Persist real records with reproducible schema changes. |
| Architecture | Framework-free entities/use cases; contracts in `application/ports`; infrastructure grouped by HTTP, persistence, security and email. HTTP DTOs and ORM mappings are separate. | Keep responsibilities cohesive and use cases independent of concrete adapters. |
| Deployment | GitHub Actions on `main`, GHCR immutable image, OCI VPS, dedicated PostgreSQL container and Caddy HTTPS. | Reuse the supplied VPS and restart containers automatically through Docker. Private owner setup remains pending. |
| Configuration | Required runtime values come from private configuration. The assistant never opens, edits or indirectly loads `.env` files. | Keep credentials under the owner's control. |
| Organizations | One active organization per account; all three institution types can donate and receive. | Type is classification, not permission. |
| Verification | Stored ADMIN role controls manual evidence review; only VERIFIED organizations participate. | Owners cannot grant themselves legitimacy or privileges. |
| Quantities | Decimal kg with gram precision; expiry uses America/Sao_Paulo. | Avoid floating-point and local-date errors. |
| Requests | Pending requests reserve nothing. Only the donor processes PENDING requests; food-row locks enforce approval limits. | Prevent over-allocation and repeated processing. |
| History | Accounts/organizations use soft deletion; food/request references and audit history remain. | Preserve traceability. Ordinary closure with linked records is blocked. |
| Sessions | Argon2 passwords, JWT plus persisted sessions; logout revokes the current session. | Server-side revocation survives API restarts. |
| Admin | One ADMIN enforced by a database constraint and serialized bootstrap. New email retires the previous admin; changed password revokes sessions. | Only the configured bootstrap identity remains admin after synchronization. |
| Recovery | Hashed, expiring, single-use tokens; generic responses and persisted attempt limits; fresh login after restoration. | Protect ownership and prevent token replay/account enumeration. |
| Metrics | Aggregate persisted records in one snapshot; separate donor/recipient roles and registered/requested/approved kg. | Prevent double-counting; approved quantity does not prove delivery or waste reduction. |
| Quality | Shared local/CI gate: secret scan, Ruff, dependency audit, real PostgreSQL tests and migration round trips. No skipped tests or disabled checks. | Passing code coverage alone is insufficient. Vendor PR checks remain independent. |
| Test data | Synthetic data and disposable databases; no real recipients contacted in automated tests. | Reproducible checks without exposing personal data or sending real messages. |

## Email delivery — selected, live setup pending

The owner selected **Gmail SMTP without a custom domain** on 2026-11-19, reopening the previously deferred delivery integration. Use a dedicated sender account, 2-Step Verification and an App Password configured privately by the owner. The adapter uses the existing recovery delivery port, verified STARTTLS, a bounded timeout and sanitized errors. No credentials belong in this document or the repository.

Google documents `smtp.gmail.com:587` with STARTTLS and personal-account limits of up to 500 messages in a rolling 24 hours: [SMTP documentation](https://developers.google.com/workspace/gmail/imap/imap-smtp). App Passwords require 2-Step Verification and may be unavailable for some restricted accounts: [account setup](https://support.google.com/accounts/answer/185833). Inbox placement and delivery time are not guaranteed.

## Still required before declaring completion

- Owner configures the sender privately and performs a controlled live delivery check.
- Close RF/RN acceptance, publish the pending security changes and resolve/recheck the GitGuardian incident.
- Publish the included Python dataset, analysis program/report and submission documentation; confirm repository access and submit through Teams.

Operational instructions: [README](README.md); deployment setup and activation limits: [production runbook](deploy/README.md). Frontend remains outside this batch.

Validation on 2026-11-19: full quality gate passed with 390 tests, including the Python dataset/analysis package; SMTP tests use fake transport only. No private configuration was read and no real email was sent. This does not replace the operator's live delivery acceptance. [Validation record](docs/VALIDATION.md).
