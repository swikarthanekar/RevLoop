"""Pure demo seed safety tests (no PostgreSQL required)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.demo.seed import (
    REQUIRED_TABLES,
    ResetNotAllowedError,
    SeedError,
    assert_reset_allowed,
    assert_schema_ready,
    seed_demo_database,
)
from app.demo.summary import format_inr
from tests.demo.conftest import postgres_url


def test_postgres_url_never_falls_back_to_database_url(monkeypatch) -> None:
    monkeypatch.delenv("REVLOOP_TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://some-host/shared")
    assert postgres_url() is None


def test_reset_refuses_production() -> None:
    prod_settings = Settings.model_construct(app_env="production", demo_mode=True)
    with pytest.raises(ResetNotAllowedError):
        assert_reset_allowed(prod_settings)


def test_reset_refuses_when_demo_mode_disabled() -> None:
    disabled = Settings.model_construct(app_env="test", demo_mode=False)
    with pytest.raises(ResetNotAllowedError):
        assert_reset_allowed(disabled)


def test_schema_missing_raises_clear_error(monkeypatch) -> None:
    class FakeInspector:
        def get_table_names(self) -> list[str]:
            return []

    settings = Settings(
        app_env="test",
        demo_mode=True,
        database_url="postgresql+psycopg://user:password@localhost:5432/revloop",
        _env_file=None,
    )
    monkeypatch.setattr("app.demo.seed.inspect", lambda _engine: FakeInspector())
    with pytest.raises(SeedError, match="Database schema is not ready"):
        seed_demo_database(reset=True, settings=settings)


def test_schema_partial_missing_raises_before_persistence(monkeypatch) -> None:
    present = sorted(REQUIRED_TABLES - {"merchant_policies"})

    class FakeInspector:
        def get_table_names(self) -> list[str]:
            return present

    settings = Settings(
        app_env="test",
        demo_mode=True,
        database_url="postgresql+psycopg://user:password@localhost:5432/revloop",
        _env_file=None,
    )
    monkeypatch.setattr("app.demo.seed.inspect", lambda _engine: FakeInspector())

    with patch("app.demo.seed._persist_spec") as persist_mock:
        with pytest.raises(SeedError, match="Missing tables: merchant_policies"):
            seed_demo_database(reset=True, settings=settings)
        persist_mock.assert_not_called()


def test_assert_schema_ready_reports_missing_tables() -> None:
    class FakeEngine:
        pass

    class FakeInspector:
        def get_table_names(self) -> list[str]:
            return sorted(REQUIRED_TABLES - {"audit_logs", "webhook_events"})

    with patch("app.demo.seed.inspect", return_value=FakeInspector()):
        with pytest.raises(SeedError, match="Missing tables: audit_logs, webhook_events"):
            assert_schema_ready(FakeEngine())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("minor", "expected"),
    [
        (499900, "₹4,999.00"),
        (3500000, "₹35,000.00"),
        (0, "₹0.00"),
    ],
)
def test_format_inr_avoids_float_arithmetic(minor: int, expected: str) -> None:
    assert format_inr(minor) == expected


def test_required_tables_covers_all_seed_tables() -> None:
    assert len(REQUIRED_TABLES) == 13
    assert "merchant_policies" in REQUIRED_TABLES
    assert "recovery_recommendations" in REQUIRED_TABLES
