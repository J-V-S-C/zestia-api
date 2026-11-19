import ast
import json
from pathlib import Path

from app.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


def imported_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_application_does_not_depend_on_adapters_or_frameworks():
    forbidden = (
        "app.infrastructure",
        "app.config",
        "fastapi",
        "pydantic",
        "sqlalchemy",
        "psycopg",
        "jwt",
        "pwdlib",
        "smtplib",
    )
    violations = [
        (str(path.relative_to(ROOT)), module)
        for path in (ROOT / "app/application").rglob("*.py")
        for module in imported_modules(path)
        if any(module == name or module.startswith(name + ".") for name in forbidden)
    ]
    assert violations == []


def test_http_resource_routes_do_not_depend_on_database_adapters():
    forbidden = ("sqlalchemy", "psycopg", "app.infrastructure.persistence")
    violations = [
        (path.name, module)
        for path in (ROOT / "app/infrastructure/http/routes").glob("*.py")
        for module in imported_modules(path)
        if any(module == name or module.startswith(name + ".") for name in forbidden)
    ]
    assert violations == []


def test_public_http_operations_match_documented_contract():
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unused@127.0.0.1:1/zestia_contract_test",
        jwt_secret="zestia-public-contract-fixture-at-least-32-characters",
        jwt_issuer="zestia-contract-test",
        jwt_audience="zestia-contract-test-api",
        access_token_minutes=15,
        cors_origins=["https://frontend.example.test"],
        admin_email="admin@example.com",
    )
    app = create_app(settings)
    try:
        operations = [
            {
                "path": path,
                "method": method,
                "status": next(int(code) for code in operation["responses"] if code != "422"),
                "tags": operation["tags"],
            }
            for path, methods in app.openapi()["paths"].items()
            for method, operation in methods.items()
        ]
        expected = json.loads((ROOT / "tests/fixtures/http_contract.json").read_text())
        assert sorted(operations, key=lambda item: (item["path"], item["method"])) == expected
    finally:
        app.state.engine.dispose()
