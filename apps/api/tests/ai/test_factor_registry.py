"""Factor registry completeness tests."""

from __future__ import annotations

from app.ai.factor_registry import (
    FACTOR_STATEMENTS,
    KNOWN_EXPLAINABLE_FACTOR_CODES,
    approved_statements_for_factors,
    render_factor_statement,
)
from app.ai.fallback import build_explanation_fallback
from app.ai.schemas import EvidenceFactorInput
from app.ai.validation import validate_explanation_semantics
from tests.ai.helpers import sample_explanation_input


def test_all_known_recovery_factors_have_deterministic_rendering() -> None:
    for code in KNOWN_EXPLAINABLE_FACTOR_CODES:
        statement = render_factor_statement(code)
        assert statement
        assert len(statement) <= 120
        assert statement == FACTOR_STATEMENTS[code]


def test_unknown_factor_uses_safe_generic_rendering() -> None:
    statement = render_factor_statement("SYNTHETIC_NEW_FACTOR")
    assert statement == "Case evidence includes synthetic new factor."


def test_model_metadata_not_rendered_for_explanation() -> None:
    statements = approved_statements_for_factors(
        [{"code": "MODEL_METADATA", "impact": "LOW", "source": "MODEL"}]
    )
    assert statements == []


def test_fallback_valid_for_every_known_explainable_factor() -> None:
    for code in KNOWN_EXPLAINABLE_FACTOR_CODES:
        factors = [{"code": code, "impact": "HIGH", "source": "TEST"}]
        statements = approved_statements_for_factors(factors)
        assert statements
        input_data = sample_explanation_input(
            approved_evidence_statements=statements,
            evidence_factors=[EvidenceFactorInput(code=code, impact="HIGH")],
        )
        explanation = build_explanation_fallback(input_data)
        validate_explanation_semantics(explanation=explanation, input_data=input_data)


def test_recovery_service_factor_universe_is_covered() -> None:
    for code in KNOWN_EXPLAINABLE_FACTOR_CODES:
        statement = render_factor_statement(code)
        assert statement
        assert len(statement) <= 120
