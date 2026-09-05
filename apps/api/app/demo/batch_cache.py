"""Cache the canonical policy simulation so a page can show it instantly.

THE PROBLEM

`run_demo_batch` regenerates the 15,000-case synthetic dataset and scores a
250-case held-out cohort. Cold, that is roughly twenty seconds; warm, under two.
A page that blocks for twenty seconds on a cold worker is not a page anyone
will wait for, and the evaluation is the single most defensible piece of
evidence the product has.

THE APPROACH

The result is fully deterministic -- same generator seed, same split, same
frozen model artifact -- so caching it is not an approximation of a fresh run,
it *is* the fresh run. The cache stores when it was computed and how long it
took, and both are shown, so a reader knows they are looking at a stored result
rather than a live one and can see it recomputed on demand.

WHAT IS NOT DONE HERE

No invalidation policy, no TTL. The inputs cannot change without a redeploy
(the dataset generator and the model artifact both ship in the image), so an
expiring cache would only add a cliff with nothing behind it. `refresh()`
exists for the explicit Recompute action.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from app.demo.batch_service import run_demo_batch
from app.demo.schemas import DemoBatchResponse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachedBatch:
    """A computed simulation plus the provenance of the computation itself."""

    result: DemoBatchResponse
    computed_at: datetime
    duration_seconds: float


#: Guards the single cached value. The batch is CPU-bound and runs in FastAPI's
#: threadpool, so two concurrent requests could otherwise both pay full cost.
#: The lock makes the second wait for the first rather than duplicate it.
_lock = threading.Lock()
_cached: CachedBatch | None = None


def _compute() -> CachedBatch:
    started = time.perf_counter()
    result = run_demo_batch()
    elapsed = time.perf_counter() - started
    return CachedBatch(
        result=result,
        computed_at=datetime.now(tz=timezone.utc),
        duration_seconds=round(elapsed, 3),
    )


def get_cached_batch() -> CachedBatch:
    """Return the cached simulation, computing it on first use."""
    global _cached
    with _lock:
        if _cached is None:
            _cached = _compute()
        return _cached


def refresh_cached_batch() -> CachedBatch:
    """Recompute and replace the cache.

    Backs the Recompute control. Running it in front of someone is the proof
    that the figures come from a live evaluation rather than a fixture, which
    is exactly the doubt a cached number invites.
    """
    global _cached
    with _lock:
        _cached = _compute()
        return _cached


def peek_cached_batch() -> CachedBatch | None:
    """The cached value if present, without computing one."""
    return _cached


def warm_cache_in_background() -> threading.Thread:
    """Start computing the simulation at application startup.

    A daemon thread so it can never hold up shutdown, and failures are logged
    rather than raised: a warm-up that fails must not stop the application from
    serving. The first request then simply pays the cold cost itself.
    """

    def _warm() -> None:
        try:
            started = time.perf_counter()
            get_cached_batch()
            logger.info(
                "Demo batch cache warmed in %.2fs.", time.perf_counter() - started
            )
        except Exception:  # noqa: BLE001 - warm-up must never break startup
            logger.warning("Demo batch cache warm-up failed.", exc_info=True)

    thread = threading.Thread(target=_warm, name="demo-batch-warmup", daemon=True)
    thread.start()
    return thread


def reset_cache_for_tests() -> None:
    """Drop the cached value. Test-support only."""
    global _cached
    with _lock:
        _cached = None


__all__ = [
    "CachedBatch",
    "get_cached_batch",
    "peek_cached_batch",
    "refresh_cached_batch",
    "reset_cache_for_tests",
    "warm_cache_in_background",
]
