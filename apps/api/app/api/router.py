"""Route registration for the HTTP layer."""

from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import health_router
from app.api.routes.razorpay_webhooks import router as razorpay_webhooks_router
from app.api.routes.recovery_actions import router as recovery_actions_router
from app.api.routes.recovery_analysis import router as recovery_analysis_router
from app.api.routes.recovery_cases import router as recovery_cases_router

api_v1_router = APIRouter(prefix="/api/v1", tags=["api"])


@api_v1_router.get("/")
def api_v1_root() -> dict[str, str]:
    return {"status": "ok", "version": "v1"}


api_v1_router.include_router(auth_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(recovery_cases_router)
api_v1_router.include_router(recovery_analysis_router)
api_v1_router.include_router(recovery_actions_router)
api_v1_router.include_router(razorpay_webhooks_router)


def build_demo_router() -> APIRouter:
    """Build the demo-only v1 router.

    Returns a fresh router each call rather than mutating the module-level
    `api_v1_router`, so an app built with demo mode on cannot leak demo routes
    into a later app built with it off.
    """
    from app.api.routes.demo import router as demo_router

    demo_api_router = APIRouter(prefix="/api/v1", tags=["api"])
    demo_api_router.include_router(demo_router)
    return demo_api_router


__all__ = ["api_v1_router", "build_demo_router", "health_router"]
