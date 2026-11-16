import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize(
    "overrides",
    [
        {"jwt_secret": "short"},
        {"jwt_secret": "replace-with-a-long-but-placeholder-secret"},
        {"database_url": "sqlite:///database.db"},
        {"access_token_minutes": 0},
        {"access_token_minutes": 1441},
    ],
)
def test_invalid_configuration_fails_before_serving_requests(overrides):
    values = {"jwt_secret": "test-secret-at-least-32-characters-long", **overrides}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
