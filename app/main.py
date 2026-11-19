from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.ports.delivery import RecoveryDelivery
from app.config import RecoverySettings, Settings, SmtpSettings
from app.infrastructure.email.smtp_recovery import SmtpRecoveryDelivery
from app.infrastructure.http.error_handlers import register_error_handlers
from app.infrastructure.http.health import router as health_router
from app.infrastructure.http.router import router
from app.infrastructure.security.jwt_tokens import TokenService
from app.infrastructure.security.passwords import Argon2PasswordHasher


def create_app(
    settings: Settings | None = None, recovery_delivery: RecoveryDelivery | None = None
) -> FastAPI:
    settings = settings or Settings()
    if recovery_delivery is None and settings.recovery_email_enabled:
        recovery_settings = RecoverySettings()
        recovery_delivery = SmtpRecoveryDelivery(
            SmtpSettings(), recovery_settings.recovery_token_minutes
        )
    engine = create_engine(
        settings.database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5}
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(title="Zestia API", version="0.1.0", lifespan=lifespan)
    app.state.recovery_delivery = recovery_delivery
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

    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(router)
    return app
