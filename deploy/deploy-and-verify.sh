#!/usr/bin/env bash
set -euo pipefail
umask 077

image=${1:?Pass the immutable registry image digest}
[[ "$image" =~ ^ghcr.io/[a-z0-9._/-]+@sha256:[a-f0-9]{64}$ ]] || {
  echo 'Deployment requires a GHCR image digest.' >&2; exit 1;
}
release_dir=$(cd -- "$(dirname -- "$0")" && pwd)
deploy_root=$(cd -- "$release_dir/../.." && pwd)
config="$deploy_root/deploy.conf"
[[ -f "$config" ]] || { echo 'Operator deployment configuration is missing.' >&2; exit 1; }
exec 9>"$deploy_root/deploy.lock"
flock -n 9 || { echo 'Another deployment is running.' >&2; exit 1; }
export ZESTIA_IMAGE="$image"
compose=(docker compose --env-file "$config" -f "$release_dir/compose.yaml")
"${compose[@]}" config --quiet
previous=''
[[ ! -f "$deploy_root/current-image" ]] || previous=$(cat "$deploy_root/current-image")
"${compose[@]}" pull
"${compose[@]}" up -d --wait --wait-timeout 120 postgres
mkdir -p "$deploy_root/backups"
backup="$deploy_root/backups/$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"
"${compose[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup"
[[ -s "$backup" ]] || { echo 'Database backup failed.' >&2; exit 1; }
"${compose[@]}" run --rm --no-deps api python -m alembic upgrade head
"${compose[@]}" run --rm --no-deps api python scripts/admin.py

rollback() {
  if [[ "$previous" =~ ^ghcr.io/[a-z0-9._/-]+@sha256:[a-f0-9]{64}$ ]]; then
    echo 'New release failed health verification; restoring previous application image.' >&2
    export ZESTIA_IMAGE="$previous"
    "${compose[@]}" up -d --wait --wait-timeout 120 api caddy || true
  else
    "${compose[@]}" stop api caddy || true
  fi
  echo "Database schema was not downgraded. Backup retained on VPS: $backup" >&2
}
if ! "${compose[@]}" up -d --wait --wait-timeout 120 api caddy; then
  rollback; exit 1
fi
# Verify the HTTPS reverse proxy, not only the internal container health check.
if ! "${compose[@]}" exec -T api python -c '
import os, time, urllib.request
deadline = time.monotonic() + 120
while True:
    try:
        with urllib.request.urlopen("https://" + os.environ["ZESTIA_SITE"] + "/health/ready", timeout=10) as response:
            assert response.status == 200
        break
    except (OSError, AssertionError):
        if time.monotonic() >= deadline:
            raise SystemExit("Public HTTPS readiness verification failed.")
        time.sleep(3)
'; then
  rollback; exit 1
fi
printf '%s\n' "$image" > "$deploy_root/current-image.next"
mv "$deploy_root/current-image.next" "$deploy_root/current-image"
echo 'Zestia deployment verified.'
