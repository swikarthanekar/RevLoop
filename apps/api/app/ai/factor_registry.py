"""Approved factor-to-statement registry for grounded explanations."""

from __future__ import annotations

NON_EXPLAINABLE_FACTOR_CODES = frozenset(
    {
        "MODEL_METADATA",
        "INFERENCE_FALLBACK",
    }
)

KNOWN_EXPLAINABLE_FACTOR_CODES = frozenset(
    {
        "ACTIVE_RAIL_DOWNTIME",
        "RECENT_METHOD_SUCCESS",
        "NO_RECENT_CONTACTS",
        "STOP_SAFE_FLOOR",
    }
)

FACTOR_STATEMENTS: dict[str, str] = {
    "ACTIVE_RAIL_DOWNTIME": "The payment rail shows active degradation.",
    "RECENT_METHOD_SUCCESS": "The customer recently succeeded with this payment method.",
    "NO_RECENT_CONTACTS": "There have been no recent recovery contacts.",
    "STOP_SAFE_FLOOR": "Stopping avoids additional recovery attempts on this case.",
}


def render_factor_statement(code: str) -> str | None:
    if code in NON_EXPLAINABLE_FACTOR_CODES:
        return None
    mapped = FACTOR_STATEMENTS.get(code)
    if mapped is not None:
        return mapped
    readable = code.replace("_", " ").strip().lower()
    if not readable:
        return None
    return f"Case evidence includes {readable}."


def approved_statements_for_factors(factors: list[dict[str, str]]) -> list[str]:
    statements: list[str] = []
    for factor in factors:
        code = str(factor.get("code", ""))
        if not code or code in NON_EXPLAINABLE_FACTOR_CODES:
            continue
        statement = render_factor_statement(code)
        if statement is not None:
            statements.append(statement)
    return statements
