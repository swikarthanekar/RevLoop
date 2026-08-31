"""Central deterministic demo seed constants."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

DEMO_SEED_VERSION = "revloop-demo-v1"

DEMO_UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

DEMO_TIMESTAMP_ANCHOR = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)

DEMO_ORGANIZATION_NAME = "Acme Learning Labs"
DEMO_ORGANIZATION_CURRENCY = "INR"
DEMO_SOURCE_LABEL = "SYNTHETIC_DEMO"

# Named logical keys
DEMO_CASE_UPI_DOWNTIME = "DEMO_CASE_UPI_DOWNTIME"
DEMO_CASE_HIGH_VALUE_APPROVAL = "DEMO_CASE_HIGH_VALUE_APPROVAL"
DEMO_CASE_RECOVERED_HISTORY = "DEMO_CASE_RECOVERED_HISTORY"

# Counts
CUSTOMER_COUNT = 64
TRANSACTION_COUNT = 640
SUBSCRIPTION_COUNT = 32
INVOICE_COUNT = 0
RECOVERY_CASE_COUNT = 100

# Case state distribution (must sum to RECOVERY_CASE_COUNT)
CASE_STATE_COUNTS: dict[str, int] = {
    "DETECTED": 8,
    "RECOMMENDED": 15,
    "AWAITING_APPROVAL": 5,
    "SCHEDULED": 5,
    "WAITING_FOR_OUTCOME": 7,
    "RECOVERED": 38,
    "FAILED": 12,
    "STOPPED": 10,
}

PAYMENT_FAILURE_CASE_COUNT = 75
SUBSCRIPTION_FAILURE_CASE_COUNT = 25

# Merchant policy (minor units)
AUTO_ACTION_LIMIT_MINOR = 1_000_000  # ₹10,000
MAX_RECOVERY_ATTEMPTS = 3
MAX_CONTACTS_PER_24H = 2
MINIMUM_AUTO_CONFIDENCE = Decimal("0.70")
COOLDOWN_MINUTES = 30

ALLOWED_ACTION_TYPES = [
    "WAIT",
    "RETRY_SAME_METHOD",
    "REQUEST_ALTERNATE_PAYMENT_METHOD",
    "CREATE_PAYMENT_LINK",
    "SEND_RECOVERY_MESSAGE",
    "ESCALATE_TO_HUMAN",
    "STOP",
]

FIRST_NAMES = (
    "Aisha",
    "Rahul",
    "Priya",
    "Arjun",
    "Neha",
    "Vikram",
    "Ananya",
    "Karan",
    "Meera",
    "Rohan",
    "Sanya",
    "Dev",
    "Isha",
    "Aditya",
    "Kavya",
)

LAST_NAMES = (
    "Sharma",
    "Patel",
    "Gupta",
    "Iyer",
    "Reddy",
    "Singh",
    "Khan",
    "Das",
    "Nair",
    "Mehta",
    "Joshi",
    "Verma",
    "Rao",
    "Malhotra",
    "Chopra",
)

PAYMENT_METHODS = ("UPI", "CARD", "NETBANKING", "WALLET")
PAYMENT_METHOD_WEIGHTS = (53, 28, 12, 7)

TRANSACTION_AMOUNTS_MINOR = (
    19900,
    49900,
    99900,
    149900,
    199900,
    249900,
    299900,
    399900,
    499900,
    999900,
    1499900,
    2499900,
    3499900,
)


def demo_uuid(stable_key: str) -> uuid.UUID:
    return uuid.uuid5(DEMO_UUID_NAMESPACE, f"{DEMO_SEED_VERSION}:{stable_key}")


def demo_timestamp(
    days_offset: int = 0,
    hours_offset: int = 0,
    minutes_offset: int = 0,
) -> datetime:
    from datetime import timedelta

    return DEMO_TIMESTAMP_ANCHOR + timedelta(
        days=days_offset, hours=hours_offset, minutes=minutes_offset
    )


# Stable exported IDs
DEMO_ORGANIZATION_ID = demo_uuid("organization:demo")
DEMO_CASE_UPI_DOWNTIME_ID = demo_uuid(f"case:{DEMO_CASE_UPI_DOWNTIME}")
DEMO_CASE_HIGH_VALUE_APPROVAL_ID = demo_uuid(f"case:{DEMO_CASE_HIGH_VALUE_APPROVAL}")
DEMO_CASE_RECOVERED_HISTORY_ID = demo_uuid(f"case:{DEMO_CASE_RECOVERED_HISTORY}")

DEMO_USER_ADMIN_ID = demo_uuid("user-profile:admin")
DEMO_USER_OPERATOR_ID = demo_uuid("user-profile:operator")
DEMO_USER_ANALYST_ID = demo_uuid("user-profile:analyst")

DEMO_AUTH_USER_ADMIN_ID = demo_uuid("auth-user:admin")
DEMO_AUTH_USER_OPERATOR_ID = demo_uuid("auth-user:operator")
DEMO_AUTH_USER_ANALYST_ID = demo_uuid("auth-user:analyst")

DEMO_MERCHANT_POLICY_ID = demo_uuid("merchant-policy:demo")
DEMO_ANALYSIS_UPI_DOWNTIME_ID = demo_uuid(f"analysis:{DEMO_CASE_UPI_DOWNTIME}")
DEMO_ANALYSIS_HIGH_VALUE_ID = demo_uuid(f"analysis:{DEMO_CASE_HIGH_VALUE_APPROVAL}")
DEMO_ANALYSIS_RECOVERED_HISTORY_ID = demo_uuid(f"analysis:{DEMO_CASE_RECOVERED_HISTORY}")
