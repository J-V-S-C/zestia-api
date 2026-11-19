import pytest

from scripts.verify import require_no_skipped_tests, require_test_database


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "not-a-url",
        "sqlite:///database_test",
        "postgresql+psycopg://test-user:test-password@localhost/application",
        "postgresql+psycopg://test-user:test-password@localhost",
    ],
)
def test_verification_rejects_missing_or_unsafe_test_database(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("TEST_DATABASE_URL", value)
    with pytest.raises(ValueError):
        require_test_database()


def test_verification_accepts_explicit_dedicated_postgres_database(monkeypatch):
    value = "postgresql+psycopg://test-user:test-password@localhost/zestia_test"
    monkeypatch.setenv("TEST_DATABASE_URL", value)
    assert require_test_database() == value


def test_verification_fails_if_any_test_is_skipped(tmp_path):
    report = tmp_path / "pytest.xml"
    report.write_text(
        "<testsuites><testsuite><testcase><skipped/></testcase></testsuite></testsuites>"
    )
    with pytest.raises(ValueError, match="skipped"):
        require_no_skipped_tests(report)


def test_verification_accepts_report_without_skipped_tests(tmp_path):
    report = tmp_path / "pytest.xml"
    report.write_text("<testsuites><testsuite><testcase/></testsuite></testsuites>")
    require_no_skipped_tests(report)
