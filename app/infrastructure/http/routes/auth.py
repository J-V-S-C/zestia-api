from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials

from app.application.errors import Unauthenticated
from app.infrastructure.http.authentication import AccountDependency, bearer
from app.infrastructure.http.dtos import (
    AccountResponse,
    LoginInput,
    RegistrationInput,
    TokenResponse,
)
from app.infrastructure.http.providers import (
    AccountRepositoryDependency,
    AuthenticationDependency,
    SessionRepositoryDependency,
)

router = APIRouter()


@router.post("/auth/register", response_model=AccountResponse, status_code=201, tags=["auth"])
def register(payload: RegistrationInput, service: AuthenticationDependency) -> AccountResponse:
    return AccountResponse.model_validate(
        service.register(str(payload.email), payload.password.get_secret_value())
    )


@router.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(
    payload: LoginInput,
    service: AuthenticationDependency,
    request: Request,
    repository: AccountRepositoryDependency,
    sessions: SessionRepositoryDependency,
) -> TokenResponse:
    account = service.login(str(payload.email), payload.password.get_secret_value())
    if repository.get_account(account.id) is None:
        raise Unauthenticated("invalid_credentials", "Email or password is incorrect.")
    token = request.app.state.tokens.issue(account.id)
    sessions.save_session(
        account.id,
        token,
        datetime.now(UTC) + timedelta(minutes=request.app.state.settings.access_token_minutes),
    )
    return TokenResponse(
        access_token=token,
        expires_in=request.app.state.settings.access_token_minutes * 60,
    )


@router.post("/auth/logout", status_code=204, tags=["auth"])
def logout(
    account: AccountDependency,
    sessions: SessionRepositoryDependency,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> Response:
    sessions.revoke_session(credentials.credentials)
    return Response(status_code=204)


@router.get("/auth/me", response_model=AccountResponse, tags=["auth"])
def me(account: AccountDependency) -> AccountResponse:
    return AccountResponse.model_validate(account)


@router.delete("/auth/me", status_code=204, tags=["auth"])
def close_account(account: AccountDependency, service: AuthenticationDependency) -> Response:
    service.close(account.id)
    return Response(status_code=204)
