# Validation record

Date: 2026-11-19. Python 3.14.7, PostgreSQL 17, isolated disposable database and synthetic configuration.

The full shared gate passed with **390 tests and zero skipped tests**. Application line/branch coverage: 99%; analysis and SMTP adapter: 100%. Ruff, formatting, installed-dependency compatibility, dependency advisory audit, redacted source/staged secret scanning, migration/model consistency and full migration downgrade/upgrade passed.

The responsibility refactor preserves all public HTTP operations and adds checks for application/framework independence and resource-route/database separation. The production Python 3.12 image was built and passed its isolated HTTP smoke flow, including migrations, admin bootstrap, non-root/read-only execution, signup/login, metrics and logout revocation. This caught and corrected an annotation compatibility issue before publication. Compose, workflow syntax (actionlint), Bash syntax, Caddy configuration and local documentation links were validated. No VPS service was changed and no registry image was published.

The included demo was executed to generate `data/demo-report.json`. Tests compare its quantities and counts with the real PostgreSQL metrics repository, and reject duplicates, bad references, self-requests and over-allocation. The snapshot is explicitly synthetic; its results are not measured city impact.

Security and business-rule evidence includes:

- Ownership, stored roles, verification gates, private request history and authenticated aggregates.
- Independent concurrent approvals, repeated processing, quantity-edit races and rollback.
- Single-admin database enforcement, concurrent bootstrap, atomic replacement/rotation and session invalidation.
- JWT signature/algorithm/claim rejection with otherwise-valid account/session records.
- Persistent session revocation verified in a fresh API process.
- Recovery expiry, replay/concurrency rejection, generic responses, limits and hashed tokens.
- SMTP certificate-verifying TLS before authentication, no-secret error messages, header-injection rejection and delivery after commit, using fake transport.
- Generated synthetic credentials that must fail secret scanning and remain redacted in logs.

Reproduce through `python scripts/verify.py` with a disposable `TEST_DATABASE_URL` ending in `_test`; see the [runbook](../README.md#verification). This run explicitly used `--env-file /dev/null`. No private environment file, application database or real email recipient was accessed. No check was bypassed.

This records local results only. It does not assert remote CI/GitGuardian clearance, live Gmail delivery, production deployment, professor access or Teams submission. The previous GitGuardian finding has not been dismissed or represented as resolved. No penetration test or absence of all vulnerabilities is claimed. [Submission notes](SUBMISSION.md) identify remaining owner actions and missing field-research details.

Public configuration templates now include every Settings/AdminBootstrapSettings/RecoverySettings/SmtpSettings field. Completed private configuration paths are ignored. The public `.env.example` is included in source/staged scanning; a generated-secret regression proves rejection and redaction while private environment files remain unopened. A local isolated container verified literal dollar/hash characters survive production configuration injection unchanged. Final shared gate: 390 passed, none skipped, 99% application coverage; HTML coverage was regenerated. No VPS access, real credentials or live email were used for these checks.

The authenticated `GET /api/v1/auth/me/organization` resolves the active organization from stored ownership. Ten PostgreSQL HTTP cases cover missing ownership, attempts to select another owner, every review state, archival/replacement, and missing/malformed/revoked/closed-account sessions. No schema migration was needed. The full gate passed with 390 tests and no skips, with 99% application coverage.

Frontend availability contract — 19/11/2026: added an authenticated aggregate read
for remaining kg and request existence, preserving private participant history and
existing food response schemas. New PostgreSQL regression covers authentication,
missing food, pending/rejected versus approved quantities, and an unrelated observer.
Full gate passed: **391 tests, zero skips, 99% coverage**, including secret scanning,
Ruff, dependency audit and migration downgrade/upgrade. Disposable database and explicit
`--env-file /dev/null`; no private configuration or production database accessed.
