from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    # TODO(Milestone 2): replace with a real database readiness check via the session layer.
    database_status = "not_checked"
    model_status = "loaded" if settings.model_bundle_path.exists() else "not_loaded"

    return {
        "status": "ok",
        "database": database_status,
        "model": model_status,
        "version": settings.api_version,
    }
