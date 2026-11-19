from fastapi import APIRouter

from app.infrastructure.http.routes import (
    auth,
    foods,
    metrics,
    organizations,
    recovery,
    requests,
    verification,
)

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(foods.router)
router.include_router(metrics.router)
router.include_router(organizations.router)
router.include_router(recovery.router)
router.include_router(requests.router)
router.include_router(verification.router)
