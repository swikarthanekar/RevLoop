from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db as get_db_session


def get_db(
    _settings: Settings = Depends(get_settings),
) -> Generator[Session, None, None]:
    yield from get_db_session(_settings)
