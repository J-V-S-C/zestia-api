import hmac
from hashlib import sha256
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.config import RecoverySettings
from app.infrastructure.http.providers import RateLimiterDependency


async def recovery_access(
    request: Request, limiter: RateLimiterDependency
) -> RecoverySettings | JSONResponse:
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
    keys = [hmac.new(secret, identifier.encode(), sha256).hexdigest() for identifier in identifiers]
    allowed = limiter.allow(keys, settings.recovery_window_seconds, settings.recovery_max_attempts)
    if not allowed:
        return JSONResponse(
            {"error": {"code": "recovery_rate_limit", "message": "Too many recovery attempts."}},
            status_code=429,
        )
    return settings


RecoveryAccess = Annotated[RecoverySettings | JSONResponse, Depends(recovery_access)]
