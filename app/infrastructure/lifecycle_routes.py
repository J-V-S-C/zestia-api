import hmac
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.application.services.recovery import RecoveryService
from app.application.services.verification import VerificationService
from app.config import RecoverySettings
from app.infrastructure.dependencies import AccountDependency, RepositoryDependency
from app.infrastructure.models import RateLimitRecord
from app.infrastructure.schemas import (
    OrganizationResponse,
    RecoveryConfirmation,
    RecoveryRequest,
    VerificationDecision,
    VerificationSubmission,
)

router = APIRouter(prefix="/api/v1")


async def recovery_access(request: Request) -> RecoverySettings | JSONResponse:
    try:
        settings = RecoverySettings()
    except ValidationError:
        return JSONResponse(
            {"error": {"code": "recovery_unavailable", "message": "Recovery is not configured."}},
            status_code=503,
        )
    identifiers = ["ip:" + (request.client.host if request.client else "unknown")]
    if request.url.path.endswith("/request"):
        try:
            body = await request.json()
        except ValueError:
            body = {}
        if isinstance(body, dict) and isinstance(body.get("email"), str):
            identifiers.append("email:" + body["email"].strip().casefold())
    secret = request.app.state.settings.jwt_secret.get_secret_value().encode()
    now = datetime.now(UTC)
    denied = False
    with request.app.state.sessions.begin() as session:
        for identifier in identifiers:
            key = hmac.new(secret, identifier.encode(), sha256).hexdigest()
            session.execute(
                insert(RateLimitRecord)
                .values(key=key, attempts=0, window_start=now)
                .on_conflict_do_nothing()
            )
            record = session.scalar(
                select(RateLimitRecord).where(RateLimitRecord.key == key).with_for_update()
            )
            if record.window_start + timedelta(seconds=settings.recovery_window_seconds) <= now:
                record.window_start, record.attempts = now, 0
            record.attempts += 1
            if record.attempts > settings.recovery_max_attempts:
                denied = True
                break
    if denied:
        return JSONResponse(
            {"error": {"code": "recovery_rate_limit", "message": "Too many recovery attempts."}},
            status_code=429,
        )
    return settings


RecoveryAccess = Annotated[RecoverySettings | JSONResponse, Depends(recovery_access)]


@router.post("/auth/recovery/request", status_code=202, tags=["auth"])
def request_recovery(
    payload: RecoveryRequest,
    request: Request,
    repository: RepositoryDependency,
    access: RecoveryAccess,
    tasks: BackgroundTasks,
):
    if isinstance(access, JSONResponse):
        return access
    delivery = request.app.state.recovery_delivery
    if delivery is None:
        return JSONResponse(
            {
                "error": {
                    "code": "recovery_unavailable",
                    "message": "Recovery delivery is not available yet.",
                }
            },
            status_code=503,
        )
    token = RecoveryService(repository).request(str(payload.email), access.recovery_token_minutes)
    if token is not None:
        tasks.add_task(delivery, str(payload.email), token)
    return {"message": "If the account is eligible, recovery instructions will be sent."}


@router.post("/auth/recovery/confirm", status_code=204, tags=["auth"])
def confirm_recovery(
    payload: RecoveryConfirmation, repository: RepositoryDependency, access: RecoveryAccess
):
    if isinstance(access, JSONResponse):
        return access
    RecoveryService(repository).restore(payload.token.get_secret_value())
    return Response(status_code=204)


@router.post(
    "/organizations/{organization_id}/verification",
    response_model=OrganizationResponse,
    tags=["verification"],
)
def submit_verification(
    organization_id: UUID,
    payload: VerificationSubmission,
    account: AccountDependency,
    repository: RepositoryDependency,
):
    return OrganizationResponse.model_validate(
        VerificationService(repository).submit(account, organization_id, payload.evidence)
    )


@router.get("/organizations/{organization_id}/verification", tags=["verification"])
def get_verification(
    organization_id: UUID, account: AccountDependency, repository: RepositoryDependency
):
    return {"evidence": VerificationService(repository).evidence(account, organization_id)}


@router.post(
    "/organizations/{organization_id}/verification/review",
    response_model=OrganizationResponse,
    tags=["verification"],
)
def review_verification(
    organization_id: UUID,
    payload: VerificationDecision,
    account: AccountDependency,
    repository: RepositoryDependency,
):
    return OrganizationResponse.model_validate(
        VerificationService(repository).review(
            account, organization_id, payload.status, payload.reason
        )
    )


@router.get(
    "/auth/me/organizations/archived",
    response_model=list[OrganizationResponse],
    tags=["organizations"],
)
def archived_organizations(
    account: AccountDependency,
    repository: RepositoryDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return [
        OrganizationResponse.model_validate(item)
        for item in repository.list_archived_organizations(account.id, offset, limit)
    ]
