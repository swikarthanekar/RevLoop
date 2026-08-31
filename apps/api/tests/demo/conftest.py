"""Shared fixtures for demo seed tests."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, normalize_database_url


def postgres_url() -> str | None:
    return os.environ.get("REVLOOP_TEST_DATABASE_URL")


def postgres_available() -> bool:
    url = postgres_url()
    if not url:
        return False
    engine = create_engine(normalize_database_url(url), pool_pre_ping=True, future=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _run_migrations(url: str) -> None:
    import os
    import subprocess
    import sys
    from pathlib import Path

    api_root = Path(__file__).resolve().parents[2]
    migration_env = os.environ.copy()
    migration_env["DATABASE_URL"] = url

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(api_root / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=str(api_root),
        env=migration_env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Alembic upgrade failed.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


@pytest.fixture(scope="session")
def postgres_engine() -> Engine | None:
    url = postgres_url()
    if not url or not postgres_available():
        return None
    return create_engine(normalize_database_url(url), pool_pre_ping=True, future=True)


@pytest.fixture(scope="session")
def migrated_postgres(postgres_engine: Engine | None) -> Engine | None:
    if postgres_engine is None:
        return None
    url = postgres_url()
    assert url is not None
    _run_migrations(url)
    return postgres_engine


@pytest.fixture
def postgres_session(migrated_postgres: Engine | None) -> Session:
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    session = sessionmaker(bind=migrated_postgres, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def demo_settings(migrated_postgres: Engine | None) -> Settings:
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    url = postgres_url()
    assert url is not None
    return Settings(app_env="test", demo_mode=True, database_url=url)
