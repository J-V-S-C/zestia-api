from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import sessionmaker

from app.application.errors import BusinessError, Forbidden, InvalidInput, NotFound, Unauthenticated
from app.config import Settings
from app.infrastructure.routes import router
from app.infrastructure.security import Argon2PasswordHasher, TokenService


def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status,
        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = create_engine(
        settings.database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5}
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(title="Zestia API", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.settings = settings
    app.state.sessions = sessionmaker(engine, expire_on_commit=False)
    app.state.hasher = Argon2PasswordHasher()
    app.state.tokens = TokenService(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

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

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready() -> dict[str, str]:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM organizations LIMIT 1"))
        return {"status": "ready"}

    app.include_router(router)
    return app
