"""Prove a built deployment artifact can still run the demo ML path.

The backend image is built from the repository root because
``app/demo/canonical_ml.py`` resolves the canonical training modules relative to
its own location (``parents[4] / "scripts"``). That coupling is invisible in
``requirements.txt`` and survives only as long as the image preserves the
repository's directory layout, so a packaging mistake would surface as a 503
from the demo batch endpoint at demo time rather than at build time.

This module runs inside the artifact and fails loudly instead. It is executed
both by the deployment smoke test against the container and by
``tests/deploy/test_runtime_packaging.py`` against a developer checkout, so the
same assertions cover both shapes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# Runnable as `python deploy/verify_runtime_packaging.py` from the apps/api
# working directory, where sys.path[0] is deploy/ rather than apps/api.
if __package__ in (None, ""):  # pragma: no cover - script entry only
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: Modules ``canonical_ml`` imports from the repository-level scripts package.
CANONICAL_MODULE_NAMES = ("common", "train_baseline", "evaluate")

#: Trees that are never part of a deployment artifact; present in a checkout.
_SKIPPED_DIRECTORIES = frozenset(
    {".venv", "venv", "node_modules", ".git", "__pycache__", ".next", "site-packages"}
)

#: The frozen Logistic Regression artifact the demo and API score against.
EXPECTED_MODEL_SHA256 = "152ecbc8ab4e5bc5b583059a824ea562363f920e238b4b7aa283d9cb74447ef2"


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def check_canonical_scripts_resolve() -> CheckResult:
    """The scripts/ml package must import from the repository-root location."""
    from app.demo.canonical_ml import _SCRIPTS_ROOT, canonical_modules

    try:
        modules = canonical_modules()
    except Exception as exc:  # noqa: BLE001 - reported, not handled
        return CheckResult(
            "canonical scripts/ml resolves",
            False,
            f"{type(exc).__name__}: {exc}",
        )

    expected_dir = (_SCRIPTS_ROOT / "ml").resolve()
    resolved = {
        name: Path(getattr(modules, name).__file__).resolve()
        for name in CANONICAL_MODULE_NAMES
    }
    misplaced = {
        name: str(path) for name, path in resolved.items() if path.parent != expected_dir
    }
    if misplaced:
        return CheckResult(
            "canonical scripts/ml resolves",
            False,
            f"expected {expected_dir}, got {misplaced}",
        )
    return CheckResult("canonical scripts/ml resolves", True, str(expected_dir))


def check_demo_batch_dependency() -> CheckResult:
    """The demo run-batch entrypoint and its canonical evaluator must import."""
    try:
        from app.demo.batch_service import run_demo_batch
        from app.demo.evaluation import run_canonical_batch
    except Exception as exc:  # noqa: BLE001 - reported, not handled
        return CheckResult(
            "demo run-batch dependency available",
            False,
            f"{type(exc).__name__}: {exc}",
        )
    return CheckResult(
        "demo run-batch dependency available",
        True,
        f"{run_demo_batch.__module__}, {run_canonical_batch.__module__}",
    )


def check_model_artifact() -> CheckResult:
    """The frozen model must be present and load through the trusted loader."""
    from app.core.config import Settings
    from app.ml.service import (
        load_trusted_model_bundle,
        resolve_trusted_model_bundle_path,
        sha256_file,
    )

    settings = Settings()
    path = resolve_trusted_model_bundle_path(settings)
    if not path.is_file():
        return CheckResult("model artifact present", False, f"missing: {path}")

    digest = sha256_file(path)
    if digest != EXPECTED_MODEL_SHA256:
        return CheckResult("model artifact present", False, f"unexpected sha256 {digest}")

    try:
        load_trusted_model_bundle(settings)
    except Exception as exc:  # noqa: BLE001 - reported, not handled
        return CheckResult("model artifact present", False, f"{type(exc).__name__}: {exc}")
    return CheckResult("model artifact present", True, f"{path} ({digest[:12]}…)")


def check_no_source_duplication() -> CheckResult:
    """The canonical modules must exist exactly once in the artifact.

    A packaging shortcut that copies scripts/ml under apps/api would satisfy the
    import while creating a second copy that no test exercises. Matching is by
    content hash rather than filename, so an unrelated module that happens to be
    called common.py is not a false positive and a renamed copy is still caught.
    """
    from app.demo.canonical_ml import _REPO_ROOT, _SCRIPTS_ROOT
    from app.ml.service import sha256_file

    expected_dir = (_SCRIPTS_ROOT / "ml").resolve()
    canonical_digests = {
        sha256_file(expected_dir / f"{name}.py"): name for name in CANONICAL_MODULE_NAMES
    }

    duplicates: list[str] = []
    for path in _REPO_ROOT.rglob("*.py"):
        if _SKIPPED_DIRECTORIES.intersection(path.parts):
            continue
        resolved = path.resolve()
        if resolved.parent == expected_dir:
            continue
        if sha256_file(resolved) in canonical_digests:
            duplicates.append(str(resolved))

    if duplicates:
        return CheckResult("no source duplication", False, f"duplicates: {duplicates}")
    return CheckResult("no source duplication", True, f"single copy under {expected_dir}")


def run_checks() -> list[CheckResult]:
    return [
        check_canonical_scripts_resolve(),
        check_demo_batch_dependency(),
        check_model_artifact(),
        check_no_source_duplication(),
    ]


def main() -> int:
    results = run_checks()
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}: {result.detail}")
    failed = [result for result in results if not result.passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} runtime packaging checks passed")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover - script entry only
    raise SystemExit(main())
