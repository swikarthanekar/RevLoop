import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory

logger = logging.getLogger(__name__)

health_router = APIRouter(tags=["health"])


def _database_status(settings: Settings) -> str:
    """Report whether the database is actually reachable.

    Deliberately opens its own short-lived session rather than depending on
    `get_db`: a failure to connect has to become the string `"unavailable"` in
    the body, and a dependency that raises would turn it into a 500 before the
    handler ever runs.

    `SELECT 1` is the cheapest statement that still proves the whole path --
    pool checkout, connection, round trip. That round trip is the point as much
    as the answer is: the pooler connection goes cold while the deployment is
    idle, so a periodic caller of this route keeps the first real request of a
    session fast.
    """
    try:
        session_factory = get_session_factory(settings)
        with session_factory() as session:
            session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # Logged at warning, not error: the process is still serving, and this
        # route's job is to report the degradation rather than to treat it as a
        # crash. `exc_info` keeps the driver's own message for diagnosis.
        logger.warning("Health check could not reach the database.", exc_info=True)
        return "unavailable"
    return "ok"


@health_router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    """Liveness and readiness in one payload, always answering `200`.

    Railway is configured to probe this path, so the status code has to mean
    "this container is serving" and nothing more. Returning 503 on an
    unreachable database would let a transient database blip restart a
    container that is otherwise healthy, or fail a deploy outright, which is a
    strictly worse outcome than serving with one field reading `unavailable`.
    Callers that care about readiness read the `database` field.
    """
    return {
        "status": "ok",
        "database": _database_status(settings),
        "model": "loaded" if settings.model_bundle_path.exists() else "not_loaded",
        "version": settings.api_version,
    }
