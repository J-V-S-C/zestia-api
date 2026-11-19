from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse

from app.infrastructure.http.dtos import (
    RecoveryConfirmation,
    RecoveryRequest,
)
from app.infrastructure.http.providers import RecoveryDependency
from app.infrastructure.http.recovery_access import RecoveryAccess

router = APIRouter()


@router.post("/auth/recovery/request", status_code=202, tags=["auth"])
def request_recovery(
    payload: RecoveryRequest,
    request: Request,
    service: RecoveryDependency,
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
    token = service.request(str(payload.email), access.recovery_token_minutes)
    if token is not None:
        tasks.add_task(delivery, str(payload.email), token)
    return {"message": "If the account is eligible, recovery instructions will be sent."}


@router.post("/auth/recovery/confirm", status_code=204, tags=["auth"])
def confirm_recovery(
    payload: RecoveryConfirmation, service: RecoveryDependency, access: RecoveryAccess
):
    if isinstance(access, JSONResponse):
        return access
    service.restore(payload.token.get_secret_value())
    return Response(status_code=204)
