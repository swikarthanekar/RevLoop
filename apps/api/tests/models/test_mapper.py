import warnings

from sqlalchemy.orm import configure_mappers

import app.models  # noqa: F401


def test_configure_mappers_without_warnings() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        configure_mappers()


def test_import_models_does_not_require_postgresql_connection() -> None:

    from app.db.base import Base

    assert len(Base.metadata.tables) == 13
