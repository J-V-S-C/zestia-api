from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.entities import Account
from app.application.errors import Unauthenticated
from app.application.services.auth import AuthenticationService
from app.application.services.foods import FoodService
from app.application.services.metrics import MetricsService
from app.application.services.organizations import OrganizationService
from app.application.services.requests import FoodRequestService
from app.infrastructure.metrics_repository import SqlAlchemyMetricsRepository
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
    if account is None or not repository.session_is_active(account.id, credentials.credentials):
        raise Unauthenticated("invalid_token", "Account no longer exists.")
    return account


AccountDependency = Annotated[Account, Depends(get_account)]


def get_organizations(repository: RepositoryDependency) -> OrganizationService:
    return OrganizationService(repository)


def get_auth(request: Request, repository: RepositoryDependency) -> AuthenticationService:
    return AuthenticationService(
        repository, request.app.state.hasher, str(request.app.state.settings.admin_email)
    )


def get_foods(repository: RepositoryDependency) -> FoodService:
    return FoodService(repository, repository)


def get_requests(repository: RepositoryDependency) -> FoodRequestService:
    return FoodRequestService(repository, repository, repository)


OrganizationsDependency = Annotated[OrganizationService, Depends(get_organizations)]
AuthenticationDependency = Annotated[AuthenticationService, Depends(get_auth)]
FoodsDependency = Annotated[FoodService, Depends(get_foods)]
RequestsDependency = Annotated[FoodRequestService, Depends(get_requests)]


def get_metrics(repository: RepositoryDependency) -> MetricsService:
    return MetricsService(SqlAlchemyMetricsRepository(repository.session))


MetricsDependency = Annotated[MetricsService, Depends(get_metrics)]
