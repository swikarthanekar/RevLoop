from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_v1_router, build_demo_router, health_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="RevLoop API", version=settings.api_version, lifespan=lifespan)

    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_v1_router)

    # Demo routes are registered only under DEMO_MODE, so they do not exist as
    # application routes otherwise and resolve to 404.
    if settings.demo_mode:
        app.include_router(build_demo_router())

    return app


app = create_app()
