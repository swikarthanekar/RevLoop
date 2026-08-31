"""Route registration for the HTTP layer."""

from fastapi import APIRouter

from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import health_router
from app.api.routes.recovery_cases import router as recovery_cases_router

api_v1_router = APIRouter(prefix="/api/v1", tags=["api"])


@api_v1_router.get("/")
def api_v1_root() -> dict[str, str]:
    return {"status": "ok", "version": "v1"}


api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(recovery_cases_router)

__all__ = ["api_v1_router", "health_router"]
