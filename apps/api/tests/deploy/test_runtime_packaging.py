"""Deployment packaging regressions.

Two layers are covered here. The runtime checks in
``deploy/verify_runtime_packaging.py`` are executed against the checkout so a
broken canonical-ML bridge fails in the normal test run, and the Dockerfile /
.dockerignore are asserted against the layout those checks depend on so the
image cannot silently stop shipping the pieces the demo needs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
ENTRYPOINT = API_ROOT / "deploy" / "entrypoint.sh"

sys.path.insert(0, str(API_ROOT / "deploy"))

import verify_runtime_packaging  # noqa: E402


@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def entrypoint_text() -> str:
    return ENTRYPOINT.read_text(encoding="utf-8")


# --- runtime checks -------------------------------------------------------


@pytest.mark.parametrize(
    "check",
    [
        verify_runtime_packaging.check_canonical_scripts_resolve,
        verify_runtime_packaging.check_demo_batch_dependency,
        verify_runtime_packaging.check_model_artifact,
        verify_runtime_packaging.check_no_source_duplication,
    ],
    ids=lambda check: check.__name__,
)
def test_runtime_packaging_check_passes(check) -> None:
    result = check()
    assert result.passed, f"{result.name}: {result.detail}"


def test_canonical_modules_load_from_the_repository_scripts_directory() -> None:
    """The bridge must reach scripts/ml, not a copy vendored under apps/api."""
    from app.demo.canonical_ml import canonical_modules

    modules = verify_runtime_packaging.CANONICAL_MODULE_NAMES
    loaded = canonical_modules()

    for name in modules:
        module_path = Path(getattr(loaded, name).__file__).resolve()
        assert module_path.parent == REPO_ROOT / "scripts" / "ml"


# --- image layout ---------------------------------------------------------


def test_dockerfile_copies_scripts_to_the_repository_root_position(
    dockerfile_text: str,
) -> None:
    """canonical_ml.py resolves parents[4]/scripts, so /app/scripts is required."""
    assert "COPY scripts/ml /app/scripts/ml" in dockerfile_text
    assert "WORKDIR /app/apps/api" in dockerfile_text


def test_dockerfile_ships_the_application_alembic_and_model_artifact(
    dockerfile_text: str,
) -> None:
    for required in ("COPY apps/api/app ./app", "COPY apps/api/alembic ./alembic"):
        assert required in dockerfile_text
    # The artifact lives inside app/ml/artifacts, so copying app/ ships it.
    assert (API_ROOT / "app" / "ml" / "artifacts" / "recovery_model.joblib").is_file()


def test_dockerfile_installs_runtime_dependencies_only(dockerfile_text: str) -> None:
    """requirements-dev.txt carries pytest, ruff and xgboost; none runs in prod."""
    install_lines = [line for line in dockerfile_text.splitlines() if "pip install" in line]

    assert install_lines
    assert all("requirements-dev" not in line for line in install_lines)
    assert "COPY apps/api/requirements.txt" in dockerfile_text


def test_dockerfile_runs_as_a_non_root_user(dockerfile_text: str) -> None:
    assert "USER revloop" in dockerfile_text


def test_dockerignore_never_excludes_the_runtime_ml_dependencies() -> None:
    patterns = [
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    forbidden = {"scripts/", "scripts", "scripts/ml/", "scripts/ml", "*.joblib", "**/*.joblib"}
    assert not forbidden.intersection(patterns)
    assert not any(pattern.startswith("apps/api/app") for pattern in patterns)


def test_dockerignore_excludes_local_virtualenv_and_node_modules() -> None:
    text = DOCKERIGNORE.read_text(encoding="utf-8")

    assert "apps/api/.venv/" in text
    assert "**/node_modules/" in text


# --- start command --------------------------------------------------------


def test_entrypoint_binds_all_interfaces_on_the_platform_port(
    entrypoint_text: str,
) -> None:
    assert "--host 0.0.0.0" in entrypoint_text
    assert '--port "${PORT:-8000}"' in entrypoint_text


def test_entrypoint_migrates_before_serving_and_fails_closed(
    entrypoint_text: str,
) -> None:
    """A failed migration must abort the deployment, not serve a stale schema."""
    assert "set -eu" in entrypoint_text

    migrate_at = entrypoint_text.index("alembic upgrade head")
    serve_at = entrypoint_text.index("exec uvicorn")
    assert migrate_at < serve_at

    assert "||" not in entrypoint_text
    assert "set +e" not in entrypoint_text


def test_entrypoint_runs_a_single_worker(entrypoint_text: str) -> None:
    assert "--workers 1" in entrypoint_text
