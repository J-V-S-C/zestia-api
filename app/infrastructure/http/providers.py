"""Compose request-scoped adapters and use cases with one database transaction."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.application.ports.repositories import AccountRepository, SessionRepository
from app.application.ports.security import RateLimiter
from app.application.services.auth import AuthenticationService
from app.application.services.foods import FoodService
from app.application.services.metrics import MetricsService
from app.application.services.organizations import OrganizationService
from app.application.services.recovery import RecoveryService
from app.application.services.requests import FoodRequestService
from app.application.services.verification import VerificationService
from app.infrastructure.persistence.accounts import SqlAlchemyAccountRepository
from app.infrastructure.persistence.foods import SqlAlchemyFoodRepository
from app.infrastructure.persistence.metrics_queries import SqlAlchemyMetricsRepository
from app.infrastructure.persistence.organizations import SqlAlchemyOrganizationRepository
from app.infrastructure.persistence.rate_limits import SqlAlchemyRateLimiter
from app.infrastructure.persistence.requests import SqlAlchemyFoodRequestRepository


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessions.begin() as session:
        yield session


SessionDependency = Annotated[Session, Depends(get_session, scope="function")]


def get_account_repository(session: SessionDependency) -> SqlAlchemyAccountRepository:
    return SqlAlchemyAccountRepository(session)


AccountRepositoryDependency = Annotated[AccountRepository, Depends(get_account_repository)]
SessionRepositoryDependency = Annotated[SessionRepository, Depends(get_account_repository)]


def get_organizations(session: SessionDependency) -> OrganizationService:
    return OrganizationService(SqlAlchemyOrganizationRepository(session))


def get_auth(request: Request, session: SessionDependency) -> AuthenticationService:
    return AuthenticationService(
        SqlAlchemyAccountRepository(session),
        request.app.state.hasher,
        str(request.app.state.settings.admin_email),
        SqlAlchemyOrganizationRepository(session),
    )


def get_foods(session: SessionDependency) -> FoodService:
    return FoodService(SqlAlchemyFoodRepository(session), SqlAlchemyOrganizationRepository(session))


def get_requests(session: SessionDependency) -> FoodRequestService:
    return FoodRequestService(
        SqlAlchemyFoodRequestRepository(session),
        SqlAlchemyFoodRepository(session),
        SqlAlchemyOrganizationRepository(session),
    )


def get_metrics(session: SessionDependency) -> MetricsService:
    return MetricsService(SqlAlchemyMetricsRepository(session))


def get_recovery(session: SessionDependency) -> RecoveryService:
    return RecoveryService(SqlAlchemyAccountRepository(session))


def get_verification(session: SessionDependency) -> VerificationService:
    return VerificationService(SqlAlchemyOrganizationRepository(session))


OrganizationsDependency = Annotated[OrganizationService, Depends(get_organizations)]
AuthenticationDependency = Annotated[AuthenticationService, Depends(get_auth)]
FoodsDependency = Annotated[FoodService, Depends(get_foods)]
RequestsDependency = Annotated[FoodRequestService, Depends(get_requests)]
MetricsDependency = Annotated[MetricsService, Depends(get_metrics)]
RecoveryDependency = Annotated[RecoveryService, Depends(get_recovery)]
VerificationDependency = Annotated[VerificationService, Depends(get_verification)]


def get_rate_limiter(request: Request) -> RateLimiter:
    return SqlAlchemyRateLimiter(request.app.state.sessions)


RateLimiterDependency = Annotated[RateLimiter, Depends(get_rate_limiter)]
