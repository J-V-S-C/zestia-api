"""Exercise the production image using disposable Docker resources and synthetic settings."""

import argparse
import json
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

POSTGRES_IMAGE = (
    "postgres:17-alpine@sha256:526f86d93c6ea08fd3f1fe5605650cacc781b2c6013169a0ad8f42c7d3d84f32"
)


def docker(*arguments: str) -> str:
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True)
    if result.returncode:
        # Do not echo container output or environment values into CI diagnostics.
        raise RuntimeError(f"Docker operation failed: {arguments[0]}")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    image = parser.parse_args().image
    name = "zestia-smoke-" + secrets.token_hex(6)
    postgres, api = name + "-postgres", name + "-api"
    credential = secrets.token_urlsafe(32)
    account_password = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory(prefix=name) as directory:
        database_config = Path(directory) / "database.fixture"
        database_config.write_text(
            "POSTGRES_USER=zestia_test\nPOSTGRES_DB=zestia_smoke_test\n"
            f"POSTGRES_PASSWORD={credential}\n"
        )
        runtime_config = Path(directory) / "runtime.fixture"
        runtime_config.write_text(
            f"DATABASE_URL=postgresql+psycopg://zestia_test:{credential}"
            "@postgres:5432/zestia_smoke_test\n"
            f"JWT_SECRET={secrets.token_urlsafe(48)}\n"
            "JWT_ISSUER=zestia-smoke\nJWT_AUDIENCE=zestia-smoke-api\n"
            "ACCESS_TOKEN_MINUTES=5\nCORS_ORIGINS=[]\n"
            "ADMIN_EMAIL=admin@example.com\n"
            f"ADMIN_PASSWORD={secrets.token_urlsafe(32)}\n"
            "RECOVERY_EMAIL_ENABLED=false\n"
        )
        database_config.chmod(0o600)
        runtime_config.chmod(0o600)
        try:
            docker("network", "create", name)
            docker(
                "run",
                "-d",
                "--name",
                postgres,
                "--network",
                name,
                "--network-alias",
                "postgres",
                "--env-file",
                str(database_config),
                "--tmpfs",
                "/var/lib/postgresql/data",
                POSTGRES_IMAGE,
            )
            deadline = time.monotonic() + 90
            while True:
                try:
                    docker(
                        "exec",
                        postgres,
                        "pg_isready",
                        "-U",
                        "zestia_test",
                        "-d",
                        "zestia_smoke_test",
                    )
                    break
                except RuntimeError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Disposable PostgreSQL did not become ready.") from None
                    time.sleep(1)
            run = ["run", "--rm", "--network", name, "--env-file", str(runtime_config)]
            docker(*run, image, "python", "-m", "alembic", "upgrade", "head")
            docker(*run, image, "python", "scripts/admin.py")
            docker(
                "run",
                "-d",
                "--name",
                api,
                "--network",
                name,
                "--env-file",
                str(runtime_config),
                "--read-only",
                "--tmpfs",
                "/tmp",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "-p",
                "127.0.0.1::8001",
                image,
            )
            assert docker("exec", api, "id", "-u") == "10001"
            port = docker("port", api, "8001/tcp").rsplit(":", 1)[1]
            base = "http://127.0.0.1:" + port

            def request(path, *, method="GET", payload=None, token=None):
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = "Bearer " + token
                data = json.dumps(payload).encode() if payload is not None else None
                req = urllib.request.Request(base + path, data, headers, method=method)
                try:
                    with urllib.request.urlopen(req, timeout=5) as response:
                        body = response.read()
                        return response.status, json.loads(body) if body else None
                except urllib.error.HTTPError as error:
                    return error.code, json.loads(error.read())

            deadline = time.monotonic() + 90
            while True:
                if docker("inspect", "--format", "{{.State.Running}}", api) != "true":
                    raise RuntimeError("Production API image exited during startup.")
                try:
                    if request("/health/ready")[0] == 200:
                        break
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError("Production API image did not become ready.")
                time.sleep(1)
            assert request("/health/live") == (200, {"status": "ok"})
            status, schema = request("/openapi.json")
            assert status == 200
            assert {"/api/v1/metrics", "/api/v1/requests"} <= schema["paths"].keys()
            credentials = {"email": "smoke@example.com", "password": account_password}
            assert request("/api/v1/auth/register", method="POST", payload=credentials)[0] == 201
            status, login = request("/api/v1/auth/login", method="POST", payload=credentials)
            assert status == 200
            token = login["access_token"]
            assert request("/api/v1/auth/me", token=token)[0] == 200
            status, metrics = request("/api/v1/metrics", token=token)
            assert status == 200 and metrics["total_organizations"] == 0
            assert request("/api/v1/auth/logout", method="POST", token=token)[0] == 204
            assert request("/api/v1/auth/me", token=token)[0] == 401
            print("Production image smoke checks passed.")
        finally:
            for container in (api, postgres):
                subprocess.run(["docker", "rm", "-f", container], capture_output=True)
            subprocess.run(["docker", "network", "rm", name], capture_output=True)


if __name__ == "__main__":
    main()
