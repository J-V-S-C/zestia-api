from fastapi import APIRouter, Depends, Request

from app.infrastructure.persistence.health import check_database

router = APIRouter(prefix="/health", tags=["health"])


def require_database(request: Request) -> None:
    check_database(request.app.state.engine)


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", dependencies=[Depends(require_database)])
def ready() -> dict[str, str]:
    return {"status": "ready"}
