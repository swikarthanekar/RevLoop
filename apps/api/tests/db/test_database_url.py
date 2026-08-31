import pytest

from app.core.config import Settings, get_settings, normalize_database_url
from app.db.session import _build_engine, _build_session_factory, get_session_factory


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    _build_engine.cache_clear()
    _build_session_factory.cache_clear()
    yield
    get_settings.cache_clear()
    _build_engine.cache_clear()
    _build_session_factory.cache_clear()


def test_normalize_database_url_preserves_psycopg_url() -> None:
    url = "postgresql+psycopg://user:password@localhost:5432/revloop"
    assert normalize_database_url(url) == url


def test_normalize_database_url_converts_postgresql_scheme() -> None:
    url = "postgresql://user:password@localhost:5432/revloop"
    assert normalize_database_url(url) == "postgresql+psycopg://user:password@localhost:5432/revloop"


def test_normalize_database_url_converts_legacy_postgres_scheme() -> None:
    url = "postgres://user:password@localhost:5432/revloop"
    assert normalize_database_url(url) == "postgresql+psycopg://user:password@localhost:5432/revloop"


def test_normalize_database_url_leaves_non_postgresql_urls_unchanged() -> None:
    url = "sqlite:///./local.db"
    assert normalize_database_url(url) == url


def test_settings_default_database_url_uses_psycopg_driver() -> None:
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+psycopg://user:password@localhost:5432/revloop"


def test_settings_normalizes_conventional_postgresql_url() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:password@localhost:5432/revloop",
    )
    assert settings.database_url == "postgresql+psycopg://user:password@localhost:5432/revloop"


def test_engine_uses_psycopg_driver_without_connecting() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:password@localhost:5432/revloop",
    )
    factory = get_session_factory(settings)
    engine = factory.kw["bind"]

    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"


def test_engine_from_conventional_postgresql_url_uses_psycopg_driver() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:password@localhost:5432/revloop",
    )
    factory = get_session_factory(settings)
    engine = factory.kw["bind"]

    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"
