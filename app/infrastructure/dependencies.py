from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.auth import AuthenticationService
from app.application.entities import Account
from app.application.errors import Unauthenticated
from app.application.services.organizations import OrganizationService
from app.infrastructure.repository import SqlAlchemyRepository

bearer = HTTPBearer(auto_error=False)


def get_repository(request: Request) -> Iterator[SqlAlchemyRepository]:
    with request.app.state.sessions.begin() as session:
        yield SqlAlchemyRepository(session)


RepositoryDependency = Annotated[SqlAlchemyRepository, Depends(get_repository, scope="function")]


def get_account(
    request: Request,
    repository: RepositoryDependency,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Account:
    if credentials is None:
        raise Unauthenticated("missing_token", "A bearer token is required.")
    account = repository.get_account(request.app.state.tokens.subject(credentials.credentials))
    if account is None:
        raise Unauthenticated("invalid_token", "Account no longer exists.")
    return account


AccountDependency = Annotated[Account, Depends(get_account)]


def get_organizations(repository: RepositoryDependency) -> OrganizationService:
    return OrganizationService(repository)


def get_auth(request: Request, repository: RepositoryDependency) -> AuthenticationService:
    return AuthenticationService(repository, request.app.state.hasher)


OrganizationsDependency = Annotated[OrganizationService, Depends(get_organizations)]
AuthenticationDependency = Annotated[AuthenticationService, Depends(get_auth)]
