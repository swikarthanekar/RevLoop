"""Supabase-shaped DATABASE_URL handling.

Supabase hands out `postgresql://` URLs, while this application is built on
SQLAlchemy 2 with psycopg 3 and needs the `postgresql+psycopg://` dialect. The
existing normalizer rewrites only the scheme, so these tests pin the parts a
deployment actually depends on: the dotted pooler username, the password, the
host/port/database, and any query string must all survive the rewrite intact.

Every credential below is a placeholder. No test may contain a real project
reference or password.
"""

from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings, normalize_database_url
from app.db.session import _build_engine, _build_session_factory, get_session_factory

PROJECT_REF = "examplerefexampleref"
PASSWORD = "placeholder-password"

#: Direct connection string, as shown by Supabase for a project database.
DIRECT_URL = f"postgresql://postgres:{PASSWORD}@db.{PROJECT_REF}.supabase.co:5432/postgres"

#: Session pooler (port 5432). This is the form a Railway backend uses, because
#: the pooler answers on IPv4 while the direct host is IPv6-only.
POOLER_URL = (
    f"postgresql://postgres.{PROJECT_REF}:{PASSWORD}"
    "@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
)


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    _build_engine.cache_clear()
    _build_session_factory.cache_clear()
    yield
    get_settings.cache_clear()
    _build_engine.cache_clear()
    _build_session_factory.cache_clear()


def test_direct_connection_url_gains_the_psycopg_dialect() -> None:
    assert normalize_database_url(DIRECT_URL) == (
        f"postgresql+psycopg://postgres:{PASSWORD}@db.{PROJECT_REF}.supabase.co:5432/postgres"
    )


def test_session_pooler_url_gains_the_psycopg_dialect() -> None:
    assert normalize_database_url(POOLER_URL) == (
        f"postgresql+psycopg://postgres.{PROJECT_REF}:{PASSWORD}"
        "@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    )


def test_dotted_pooler_username_survives_normalization() -> None:
    """The pooler username is `postgres.<project-ref>`; the dot must not be lost."""
    url = make_url(normalize_database_url(POOLER_URL))

    assert url.username == f"postgres.{PROJECT_REF}"
    assert url.password == PASSWORD
    assert url.host == "aws-0-ap-south-1.pooler.supabase.com"
    assert url.port == 5432
    assert url.database == "postgres"


def test_sslmode_query_parameter_is_preserved() -> None:
    normalized = normalize_database_url(f"{DIRECT_URL}?sslmode=require")

    assert normalized.startswith("postgresql+psycopg://")
    assert normalized.endswith("?sslmode=require")
    assert make_url(normalized).query["sslmode"] == "require"


def test_an_already_normalized_supabase_url_is_left_alone() -> None:
    url = POOLER_URL.replace("postgresql://", "postgresql+psycopg://", 1)

    assert normalize_database_url(url) == url


def test_legacy_postgres_scheme_from_a_pooler_url_is_normalized() -> None:
    url = POOLER_URL.replace("postgresql://", "postgres://", 1)

    assert normalize_database_url(url).startswith("postgresql+psycopg://postgres.")


def test_settings_normalize_a_supabase_pooler_url() -> None:
    settings = Settings(_env_file=None, database_url=POOLER_URL)

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_engine_from_a_supabase_pooler_url_uses_psycopg_without_connecting() -> None:
    settings = Settings(_env_file=None, database_url=POOLER_URL)
    engine = get_session_factory(settings).kw["bind"]

    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"
    assert engine.url.host == "aws-0-ap-south-1.pooler.supabase.com"


def test_unknown_query_parameters_are_passed_through_unchanged() -> None:
    """Documents why deployment must use a pooler URL without `pgbouncer=true`.

    The normalizer rewrites the scheme and nothing else, so a libpq-unknown
    parameter reaches the driver and fails at connect time. Deployment
    documentation therefore specifies which connection string to copy rather
    than the normalizer quietly editing the operator's URL.
    """
    normalized = normalize_database_url(f"{POOLER_URL}?pgbouncer=true")

    assert normalized.endswith("?pgbouncer=true")
