"""Scan version-controlled source without opening private environment files."""

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def scan_secrets() -> None:
    scanner = shutil.which("gitleaks") or str(ROOT / ".venv/bin/gitleaks")
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
        )
        .decode()
        .split("\0")
    )
    with tempfile.TemporaryDirectory(prefix="zestia-source-scan-") as directory:
        destination = Path(directory)
        for name in set(paths) - {""}:
            path = Path(name)
            if path.name == ".env" or path.name.startswith(".env."):
                if path.name != ".env.example":
                    raise ValueError("Private environment file must not be version controlled.")
                # Only the explicitly authorized public template may be read and scanned.
            source = ROOT / path
            if source.is_symlink():
                raise ValueError(f"Cannot safely scan symbolic link: {name}")
            if source.is_file():
                target = destination / "working" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            staged = subprocess.run(
                ["git", "show", f":{name}"], cwd=ROOT, capture_output=True, check=False
            )
            if staged.returncode == 0:
                target = destination / "staged" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(staged.stdout)
        subprocess.run(
            [
                scanner,
                "dir",
                "--config",
                str(ROOT / ".gitleaks.toml"),
                "--redact",
                "--verbose",
                "--no-banner",
                str(destination),
            ],
            check=True,
        )


if __name__ == "__main__":
    scan_secrets()
