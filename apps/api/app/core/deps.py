from collections.abc import Generator
from typing import Any

from fastapi import Depends

from app.core.config import Settings, get_settings


def get_db(_settings: Settings = Depends(get_settings)) -> Generator[None, None, None]:
    """Database session placeholder until Milestone 2."""
    yield None


def get_db_session() -> Any:
    """Non-route helper placeholder for future SQLAlchemy session wiring."""
    return None
