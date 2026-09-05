"""Demo-only endpoints (API_CONTRACTS.md section 12).

These routes exist only when ``DEMO_MODE=true``. Registration is conditional in
``app.api.router``, so with demo mode disabled the paths are not part of the
application at all and FastAPI answers 404 — the route genuinely does not exist
rather than existing and refusing. Both operations additionally require ADMIN.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, get_current_user
from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.core.errors import ForbiddenError
from app.demo.batch_cache import get_cached_batch, refresh_cached_batch
from app.demo.batch_service import describe_reset, run_demo_batch
from app.demo.schemas import (
    DemoBatchCachedResponse,
    DemoBatchResponse,
    DemoResetResponse,
)
from app.demo.seed import seed_demo_database
from app.domain.enums import UserRole

router = APIRouter(prefix="/demo", tags=["demo"])

_DEMO_ROLES = frozenset({UserRole.ADMIN})


async def require_demo_admin(
    current_user: Annotated[AuthContext, Depends(get_current_user)],
) -> AuthContext:
    """ADMIN gate for demo operations.

    Reuses the shared `get_current_user` dependency; the role comes from the
    server-resolved auth context, never from the request body.
    """
    if current_user.role not in _DEMO_ROLES:
        raise ForbiddenError(
            code="ROLE_NOT_ALLOWED",
            message="Demo operations require ADMIN role.",
        )
    return current_user


@router.post("/reset", response_model=DemoResetResponse, status_code=status.HTTP_200_OK)
async def reset_demo(
    _current_user: Annotated[AuthContext, Depends(require_demo_admin)],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DemoResetResponse:
    """Restore the canonical deterministic demo state.

    `seed_demo_database(reset=True)` deletes the demo tenant and reseeds it in a
    single transaction, so a failure mid-way rolls back rather than publishing a
    half-reset database. Externally provisioned `user_profiles` rows are carried
    across the rebuild, so a reset can never lock a real account out of the
    tenant it administers.

    Refusal by `assert_reset_allowed` raises `ResetNotAllowedError`, which is an
    `AppError`, so a blocked reset answers `403` with a specific code rather
    than an opaque `500`.
    """
    result = seed_demo_database(reset=True, settings=settings)
    # The reset committed on its own session; expire ours so the counts below
    # reflect the newly seeded rows rather than a stale identity map.
    session.expire_all()
    return describe_reset(
        session,
        result.reset_performed,
        preserved_user_profiles=result.preserved_user_profiles,
    )


@router.get(
    "/evaluation",
    response_model=DemoBatchCachedResponse,
    status_code=status.HTTP_200_OK,
)
def read_evaluation(
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
) -> DemoBatchCachedResponse:
    """Serve the cached held-out policy simulation.

    Readable by any authenticated role, unlike the ADMIN-gated operations
    below: this returns a stored, read-only evaluation and changes nothing.

    The cache is normally warmed at startup, so this answers immediately. If
    warm-up has not finished the first caller computes it, which is slower but
    correct -- never a placeholder or a stale stand-in.
    """
    cached = get_cached_batch()
    return DemoBatchCachedResponse(
        evaluation=cached.result,
        computed_at=cached.computed_at,
        duration_seconds=cached.duration_seconds,
        recomputed=False,
    )


@router.post(
    "/evaluation/recompute",
    response_model=DemoBatchCachedResponse,
    status_code=status.HTTP_200_OK,
)
def recompute_evaluation(
    _current_user: Annotated[AuthContext, Depends(require_demo_admin)],
) -> DemoBatchCachedResponse:
    """Re-run the simulation and replace the cache.

    ADMIN-gated not because it mutates business data -- it touches none -- but
    because it is several seconds of CPU that anyone could otherwise trigger
    repeatedly.

    Its real purpose is evidential: running it in front of a reader, and
    watching `computed_at` move while every figure stays identical, demonstrates
    both that the evaluation is live and that it is deterministic.
    """
    cached = refresh_cached_batch()
    return DemoBatchCachedResponse(
        evaluation=cached.result,
        computed_at=cached.computed_at,
        duration_seconds=cached.duration_seconds,
        recomputed=True,
    )


@router.post("/run-batch", response_model=DemoBatchResponse, status_code=status.HTTP_200_OK)
def run_batch(
    _current_user: Annotated[AuthContext, Depends(require_demo_admin)],
) -> DemoBatchResponse:
    """Run the canonical synthetic policy simulation over the canonical cohort.

    Pure simulation: no database read of business tables, no provider adapter,
    no writes, so repeated submissions cannot accumulate state.

    Declared `def` rather than `async def` on purpose. The work is synchronous
    CPU-bound scoring that takes seconds, so FastAPI runs it in its threadpool
    instead of blocking the event loop. The reset route stays `async def`
    because its work is short.
    """
    return run_demo_batch()
