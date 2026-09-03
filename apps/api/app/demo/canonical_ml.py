"""Single controlled bridge to the canonical Prompt 10/11 synthetic ML pipeline.

Prompt 23 must not own a second synthetic world. The canonical synthetic
generator (Prompt 10) and the canonical offline policy simulator (Prompt 11)
already exist under ``scripts/ml`` and are the accepted implementations that the
frozen Logistic Regression was trained and evaluated against. This module is the
only place that reaches them, so there is exactly one methodology in the
repository.

WHY A PATH BRIDGE

``scripts/ml/common.py`` imports *from* ``app`` (``app.domain.enums``,
``app.recovery.candidates``, ``app.recovery.schemas``). The dependency direction
is therefore ``scripts -> app``, and ``scripts`` is not an installed package on
the API's import path. Reaching back the other way needs an explicit path entry.
The repository already establishes exactly this bridge in
``apps/api/tests/ml/test_synthetic_data.py`` and in
``scripts/ml/evaluate.py::_configure_import_paths``.

Only side-effect-free modules are imported here. ``ml.common``,
``ml.train_baseline`` and ``ml.evaluate`` define constants and functions at
import time; none of them mutates ``sys.path`` or performs work on import. The
CLI entrypoints (``ml.generate_training_data``, ``ml.evaluate.main``) are never
imported or invoked.

Known limitation, reported rather than hidden: this makes the demo-only batch
endpoint depend on ``scripts/`` being present alongside ``apps/api``. That is
acceptable because the endpoint exists only under ``DEMO_MODE`` and is an
offline evaluation tool, not a production revenue path. If ``scripts/`` is
absent the batch fails closed through the normal error envelope rather than
silently degrading to a different methodology.
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.errors import AppError

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

#: ``app/demo/canonical_ml.py`` -> app -> api -> apps -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPTS_ROOT = _REPO_ROOT / "scripts"


class CanonicalEvaluationUnavailableError(AppError):
    """Raised when the canonical synthetic evaluation cannot be performed.

    The batch fails closed. It never falls back to a different scorer or a
    different synthetic world, because a benchmark built from a substitute would
    be reported under the selected model's name.
    """

    def __init__(self, *, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="CANONICAL_EVALUATION_UNAVAILABLE",
            message=message,
            status_code=503,
            details=details or {},
        )


def _ensure_scripts_on_path() -> None:
    scripts_path = str(_SCRIPTS_ROOT)
    if not _SCRIPTS_ROOT.is_dir():
        raise CanonicalEvaluationUnavailableError(
            message="Canonical synthetic ML package is not available.",
        )
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)


@dataclass(frozen=True)
class CanonicalModules:
    """The canonical Prompt 10/11 callables, imported once."""

    common: Any
    train_baseline: Any
    evaluate: Any


@lru_cache(maxsize=1)
def canonical_modules() -> CanonicalModules:
    """Import the canonical modules. Cached; import is side-effect free."""
    _ensure_scripts_on_path()
    try:
        from ml import common, evaluate, train_baseline
    except ImportError as exc:  # pragma: no cover - defensive
        raise CanonicalEvaluationUnavailableError(
            message="Canonical synthetic ML package could not be imported.",
        ) from exc
    return CanonicalModules(common=common, train_baseline=train_baseline, evaluate=evaluate)


@dataclass(frozen=True)
class CanonicalDataset:
    """The canonical Prompt 10 dataset loaded through the canonical reader."""

    frame: pd.DataFrame
    summary: dict[str, Any]
    dataset_version: str
    feature_schema_version: str
    seed: int
    split_seed: int


@lru_cache(maxsize=1)
def canonical_dataset() -> CanonicalDataset:
    """Regenerate and load the canonical synthetic dataset deterministically.

    The dataset CSV is intentionally not committed, so it is regenerated with the
    canonical generator at the canonical seed and case count, then read back
    through the canonical ``load_training_frame`` reader. Going through the
    reader (rather than building a DataFrame from raw rows) guarantees the exact
    dtypes and column validation the Prompt 11 evaluator was accepted against.

    The temporary directory is removed immediately; nothing is written into the
    repository.
    """
    modules = canonical_modules()
    common = modules.common
    train_baseline = modules.train_baseline

    dataset = common.generate_dataset(
        case_count=common.DEFAULT_CASE_COUNT,
        seed=common.DEFAULT_SEED,
    )
    with tempfile.TemporaryDirectory(prefix="revloop-demo-batch-") as directory:
        csv_path, summary_path = common.write_dataset(Path(directory), dataset)
        frame, summary = train_baseline.load_training_frame(
            csv_path=csv_path,
            summary_path=summary_path,
        )
    train_baseline.validate_split_integrity(frame)

    return CanonicalDataset(
        frame=frame,
        summary=summary,
        dataset_version=str(summary["dataset_version"]),
        feature_schema_version=str(summary["feature_schema_version"]),
        seed=int(summary["seed"]),
        split_seed=int(summary["split_seed"]),
    )


def canonical_test_case_ids() -> tuple[str, ...]:
    """Canonical TEST-split case IDs in stable sorted order.

    Sorting is policy-independent and depends only on the generated IDs, so the
    cohort cannot shift based on any evaluation outcome.
    """
    frame = canonical_dataset().frame
    test_rows = frame.loc[frame["split"] == "test"]
    return tuple(sorted(test_rows["case_id"].astype(str).unique()))


__all__ = [
    "CanonicalDataset",
    "CanonicalEvaluationUnavailableError",
    "CanonicalModules",
    "canonical_dataset",
    "canonical_modules",
    "canonical_test_case_ids",
]
