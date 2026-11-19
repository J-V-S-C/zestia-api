from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.entities import Account
from app.application.errors import Unauthenticated
from app.infrastructure.http.providers import (
    AccountRepositoryDependency,
    SessionRepositoryDependency,
)

bearer = HTTPBearer(auto_error=False)


def get_account(
    request: Request,
    accounts: AccountRepositoryDependency,
    sessions: SessionRepositoryDependency,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Account:
    if credentials is None:
        raise Unauthenticated("missing_token", "A bearer token is required.")
    account = accounts.get_account(request.app.state.tokens.subject(credentials.credentials))
    if account is None or not sessions.session_is_active(account.id, credentials.credentials):
        raise Unauthenticated("invalid_token", "Account no longer exists.")
    return account


AccountDependency = Annotated[Account, Depends(get_account)]
