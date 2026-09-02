"""Fixtures for AI unit tests (no PostgreSQL required by default)."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.demo.constants import DEMO_AUTH_USER_ANALYST_ID, DEMO_ORGANIZATION_ID


@pytest.fixture
def recovery_demo_settings() -> Settings:
    return Settings(
        app_env="test",
        demo_mode=True,
        dev_auth_user_id=DEMO_AUTH_USER_ANALYST_ID,
        dev_auth_organization_id=DEMO_ORGANIZATION_ID,
    )
