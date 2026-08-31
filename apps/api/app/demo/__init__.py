"""Deterministic synthetic demo seed for RevLoop development."""

from app.demo.constants import (
    DEMO_CASE_HIGH_VALUE_APPROVAL_ID,
    DEMO_CASE_RECOVERED_HISTORY_ID,
    DEMO_CASE_UPI_DOWNTIME_ID,
    DEMO_ORGANIZATION_ID,
    DEMO_SEED_VERSION,
)
from app.demo.factory import build_demo_seed_spec
from app.demo.seed import delete_demo_tenant, seed_demo_database

__all__ = [
    "DEMO_CASE_HIGH_VALUE_APPROVAL_ID",
    "DEMO_CASE_RECOVERED_HISTORY_ID",
    "DEMO_CASE_UPI_DOWNTIME_ID",
    "DEMO_ORGANIZATION_ID",
    "DEMO_SEED_VERSION",
    "build_demo_seed_spec",
    "delete_demo_tenant",
    "seed_demo_database",
]
