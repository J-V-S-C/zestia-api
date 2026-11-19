# Production on OCI

The deployment workflow is implemented; **production has not been activated**. It targets the existing x86 VPS, runs PostgreSQL in a dedicated container and exposes only Caddy on ports 80/443. The API retains port 8001 inside Docker; PostgreSQL and the API have no public host ports. Existing VPS applications are separate.

**Access revoked by the owner on 2026-11-19.** The GitHub `OCI_SSH_KEY` and `OCI_KNOWN_HOSTS` secrets were deleted. The generated local temporary key directory is gone; the redacted working/staged source scan found no leaks. The assistant is forbidden from connecting to the VPS or opening credentials. The owner must remove the public-key entry ending in `zestia-github-actions` from the VPS authorized keys; remote removal has not been performed or claimed. Earlier setup details below are historical. Deployment now requires owner-managed credentials and explicit owner action; do not recreate credentials automatically.

Setup checked on 2026-11-19: Docker is enabled/active; `simulador-api.service` owns port 8000; ports 80/443 were free. DNS resolves to the VPS, GHCR responds and Gmail STARTTLS verifies successfully. The GitHub `production` environment now permits deployments from `main` and contains the three deployment variables plus both SSH secrets. A dedicated deployment key was authorized and tested against the owner-supplied host fingerprint. `/opt/zestia`, `releases/` and the nonsecret `deploy.conf` were created. Private database/application files are still absent; no Zestia application was started. Host firewall rules allow TCP 80/443; OCI ingress and public HTTPS still require live verification.

Main initially had no branch protection. A required-check policy update was requested, but that request and its follow-up read timed out; its current state is unconfirmed. Verify that both Python checks, `Verify production image` and `GitGuardian Security Checks` are required before merging. No vendor finding was dismissed.

Pushes to `main` (or manual dispatch on `main`) run the shared Python verification and production-image checks before publishing. The exact smoke-tested image is pushed to GHCR, then deployed by digest over host-verified SSH. The VPS script serializes deployments, backs up PostgreSQL, applies migrations, synchronizes the single admin, starts the release and checks public HTTPS. It retains the previous image for recovery after a failed startup or HTTPS check. It does not downgrade schemas or undo committed bootstrap changes; migrations must remain compatible with the previous application. Failed migration/bootstrap stops deployment before replacing the running API. There is no zero-downtime guarantee.

Containers use `restart: unless-stopped`; the enabled Docker daemon starts them after reboot. A separate application systemd service is unnecessary. Caddy obtains and renews certificates using persistent `/data`. The API trusts proxy headers because it is reachable only on the private Compose network; do not publish its port without changing that trust policy.

## Owner configuration

No assistant read, changed or loaded private environment files. Private values must be created by the owner on the server and excluded from Git. The workflow does not create application credentials.

The public, fill-in templates are [database.conf.example](database.conf.example) and [application.conf.example](application.conf.example). On the VPS, the owner creates `/opt/zestia/database.conf` and `/opt/zestia/application.conf` from these templates, fills the empty fields privately, and restricts their permissions to mode 600. Use matching database credentials in both files and `postgres:5432` in `DATABASE_URL`. To enable Gmail, fill the sender/App Password and change `RECOVERY_EMAIL_ENABLED` to true. Keep existing credentials when reusing an existing database or admin. Do not send either completed file to the assistant.

For automatic deployment, the owner must configure GitHub's `OCI_SSH_KEY` and `OCI_KNOWN_HOSTS` secrets using credentials they control; the previously generated secrets have been deleted. The workflow cannot deploy with those secrets absent. After the reviewed code reaches `main`, a successful deployment must leave `https://<configured-hostname>/health/ready` returning HTTP 200 with a valid HTTPS certificate. A recovery request must deliver an email to an owner-controlled test account. These are the concrete remaining live checks; no outside business approver is required by the implementation.

Use a dedicated `/opt/zestia` directory, owned by the deployment user, with private files mode 600 and directories mode 750. Set GitHub production environment variables:

| Variable | Value |
|---|---|
| `OCI_HOST` | `147.15.69.216` |
| `OCI_SSH_USER` | `ubuntu` |
| `OCI_DEPLOY_DIR` | `/opt/zestia` |

Set environment secrets `OCI_SSH_KEY` (the authorized private key) and `OCI_KNOWN_HOSTS` (host key independently verified against the VPS). Keep production environment approval and branch protection enabled; require the verification and vendor security checks. `GITHUB_TOKEN` handles GHCR publication and temporary server pull authentication; registry credentials are removed after the deployment command.

The now-revoked deployment key was dedicated to GitHub Actions and had SSH forwarding/PTY restrictions. Remove only its matching public-key entry from the deployment user's `authorized_keys`, preserving the owner's existing keys. No assistant credential creation or rotation is authorized.

Create `/opt/zestia/deploy.conf` with **nonsecret** Compose settings:

```ini
ZESTIA_PROJECT_NAME=zestia-production
ZESTIA_DATABASE_CONFIG=/opt/zestia/database.conf
ZESTIA_RUNTIME_CONFIG=/opt/zestia/application.conf
ZESTIA_SITE=zestia.147.15.69.216.sslip.io
```

The selected hostname resolves to the supplied VPS without purchasing a domain. DNS availability and public-certificate issuance are external dependencies; a controlled domain can replace it later. Allow inbound TCP 80/443 and optionally UDP 443 in OCI networking and the host firewall; SSH must remain available. Check that no other service owns these ports. Do not open PostgreSQL or API ports.

The private `database.conf` requires `POSTGRES_DB`, `POSTGRES_USER` and a generated `POSTGRES_PASSWORD`. The private `application.conf` requires all settings in the [backend runbook](../README.md), including `ADMIN_EMAIL`, `ADMIN_PASSWORD` and a generated JWT secret. Its `DATABASE_URL` must use `postgres:5432` and matching database credentials (URL-encode reserved characters). Configure Gmail/recovery values privately when enabling delivery. Keep `PYTHON_DOTENV_DISABLED=1`; Docker injects the variables directly. Do not commit or print either file. Changing database credentials does not automatically update an existing PostgreSQL volume.

After the owner supplies these values, merge the reviewed workflow to `main` and dispatch deployment. No DNS certificate, live email or production readiness is claimed before that succeeds. The expected readiness URL is `https://zestia.147.15.69.216.sslip.io/health/ready`.

## Verification and recovery

Local/CI smoke verification uses only generated synthetic settings, an ephemeral PostgreSQL database and a loopback HTTP port:

```sh
docker build -t zestia:predeploy .
python scripts/smoke_image.py zestia:predeploy
```

It checks migrations, admin bootstrap, non-root/read-only execution, readiness, Swagger paths, signup/login, metrics and logout revocation. All disposable containers/networks are removed afterward. It does not send email or test public certificate issuance.

Backups remain under `/opt/zestia/backups`; they contain private application data and need operator-controlled retention and off-server copies. Image rollback is automatic only after the new API starts failing health/HTTPS checks. Database restore requires a deliberate maintenance procedure; restoring over active data is never automatic. No volume is pruned by deployment. If recovery needs different manifests, use the retained release directory with the prior image digest and the same Compose project/configuration. Avoid concurrent manual changes while a release is running.
