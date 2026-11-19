from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from app.application.errors import BusinessError, Forbidden, InvalidInput, NotFound, Unauthenticated


def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status,
        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessError)
    async def business_error(request: Request, error: BusinessError) -> JSONResponse:
        statuses = {InvalidInput: 422, NotFound: 404, Forbidden: 403, Unauthenticated: 401}
        return error_response(error.code, str(error), statuses.get(type(error), 409))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        details = [
            {"location": list(item["loc"]), "message": item["msg"]} for item in error.errors()
        ]
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Invalid input.",
                    "details": details,
                }
            },
            status_code=422,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, error: IntegrityError) -> JSONResponse:
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint == "accounts_email_key":
            return error_response("email_registered", "Email is already registered.", 409)
        if constraint == "organizations_active_owner_key":
            return error_response(
                "organization_exists", "An account can own only one organization.", 409
            )
        return error_response("data_conflict", "Operation conflicts with stored data.", 409)

    @app.exception_handler(OperationalError)
    @app.exception_handler(ProgrammingError)
    async def unavailable_database(request: Request, error: Exception) -> JSONResponse:
        return error_response(
            "database_unavailable", "Database is unavailable or migrations are missing.", 503
        )
