"""Route registration for the HTTP layer."""

from fastapi import APIRouter

from app.api.routes.health import health_router

api_v1_router = APIRouter(prefix="/api/v1", tags=["api"])


@api_v1_router.get("/")
def api_v1_root() -> dict[str, str]:
    return {"status": "ok", "version": "v1"}


__all__ = ["api_v1_router", "health_router"]
