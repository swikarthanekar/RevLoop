from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings, normalize_database_url


@lru_cache
def _build_engine(database_url: str) -> Engine:
    return create_engine(
        normalize_database_url(database_url),
        pool_pre_ping=True,
        future=True,
    )


@lru_cache
def _build_session_factory(database_url: str) -> sessionmaker[Session]:
    engine = _build_engine(database_url)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    resolved = settings or get_settings()
    return _build_session_factory(resolved.database_url)


def get_db(settings: Settings | None = None) -> Generator[Session, None, None]:
    session_factory = get_session_factory(settings)
    session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
