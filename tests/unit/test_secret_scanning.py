import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import scan_secrets as scanner_module
from scripts.scan_secrets import scan_secrets

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["source.py", "tests/fixtures/ci.env"])
def test_secret_scanner_blocks_and_redacts_generated_credentials(tmp_path, name):
    token = secrets.token_urlsafe(48)
    fixture = tmp_path / name
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text(f'api_key = "{token}"\n')
    scanner = shutil.which("gitleaks") or str(ROOT / ".venv/bin/gitleaks")
    result = subprocess.run(
        [
            scanner,
            "dir",
            "--config",
            str(ROOT / ".gitleaks.toml"),
            "--redact",
            "--verbose",
            "--no-banner",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "generic-api-key" in result.stdout + result.stderr
    assert token not in result.stdout + result.stderr


def test_private_environment_paths_are_rejected_without_opening_them(monkeypatch):
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: b".env\0")
    with pytest.raises(ValueError, match="Private environment file"):
        scan_secrets()


def test_public_environment_template_is_scanned_and_findings_are_redacted(
    tmp_path, monkeypatch, capfd
):
    token = secrets.token_urlsafe(48)
    scanner = shutil.which("gitleaks") or str(ROOT / ".venv/bin/gitleaks")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".env.example").write_text(f'api_key = "{token}"\n')
    shutil.copyfile(ROOT / ".gitleaks.toml", tmp_path / ".gitleaks.toml")
    subprocess.run(["git", "add", "--", ".env.example"], cwd=tmp_path, check=True)
    monkeypatch.setattr(scanner_module, "ROOT", tmp_path)
    monkeypatch.setattr(scanner_module.shutil, "which", lambda name: scanner)
    with pytest.raises(subprocess.CalledProcessError):
        scan_secrets()
    output = capfd.readouterr()
    assert "generic-api-key" in output.out + output.err
    assert token not in output.out + output.err
