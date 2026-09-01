"""Prompt 12 model-selection helper regression tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
for path in (REPO_ROOT / "apps" / "api", REPO_ROOT / "scripts"):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from ml.common import (  # noqa: E402,I001
    RUNTIME_MODEL_LOGISTIC_REGRESSION,
    RUNTIME_MODEL_XGBOOST,
    select_runtime_model,
)


def _policy(expected: float) -> dict:
    return {"expected_synthetic_recovered_minor": expected}


def _metrics(*, pr_auc: float, brier: float, log_loss: float) -> dict:
    return {
        "pr_auc": pr_auc,
        "brier_score": brier,
        "log_loss": log_loss,
    }


def test_exact_tie_keeps_logistic_regression() -> None:
    base = _metrics(pr_auc=0.5563, brier=0.1564, log_loss=0.4768)
    result = select_runtime_model(
        logistic_regression_test_metrics=base,
        xgboost_test_metrics=base,
        logistic_regression_policy=_policy(1_000),
        xgboost_policy=_policy(1_000),
    )
    assert result.selected_model == RUNTIME_MODEL_LOGISTIC_REGRESSION
    assert "no_material_win" in result.selection_reason_codes


def test_marginal_xgboost_improvement_keeps_logistic_regression() -> None:
    result = select_runtime_model(
        logistic_regression_test_metrics=_metrics(
            pr_auc=0.5563,
            brier=0.1564,
            log_loss=0.4768,
        ),
        xgboost_test_metrics=_metrics(
            pr_auc=0.5600,
            brier=0.1550,
            log_loss=0.4720,
        ),
        logistic_regression_policy=_policy(1_000_000),
        xgboost_policy=_policy(1_005_000),
    )
    assert result.selected_model == RUNTIME_MODEL_LOGISTIC_REGRESSION


def test_material_pr_auc_win_without_guardrail_selects_xgboost() -> None:
    result = select_runtime_model(
        logistic_regression_test_metrics=_metrics(
            pr_auc=0.5563,
            brier=0.1564,
            log_loss=0.4768,
        ),
        xgboost_test_metrics=_metrics(
            pr_auc=0.5720,
            brier=0.1540,
            log_loss=0.4700,
        ),
        logistic_regression_policy=_policy(1_000_000),
        xgboost_policy=_policy(1_020_000),
    )
    assert result.selected_model == RUNTIME_MODEL_XGBOOST
    assert "pr_auc" in result.material_wins


def test_material_policy_value_win_without_guardrail_selects_xgboost() -> None:
    result = select_runtime_model(
        logistic_regression_test_metrics=_metrics(
            pr_auc=0.5563,
            brier=0.1564,
            log_loss=0.4768,
        ),
        xgboost_test_metrics=_metrics(
            pr_auc=0.5563,
            brier=0.1564,
            log_loss=0.4768,
        ),
        logistic_regression_policy=_policy(1_000_000_000),
        xgboost_policy=_policy(1_020_000_000),
    )
    assert result.selected_model == RUNTIME_MODEL_XGBOOST
    assert "expected_recovered" in result.material_wins


def test_material_win_with_brier_guardrail_keeps_logistic_regression() -> None:
    result = select_runtime_model(
        logistic_regression_test_metrics=_metrics(
            pr_auc=0.5563,
            brier=0.1564,
            log_loss=0.4768,
        ),
        xgboost_test_metrics=_metrics(
            pr_auc=0.5720,
            brier=0.1600,
            log_loss=0.4700,
        ),
        logistic_regression_policy=_policy(1_000_000),
        xgboost_policy=_policy(1_020_000),
    )
    assert result.selected_model == RUNTIME_MODEL_LOGISTIC_REGRESSION
    assert "brier_score" in result.guardrail_failures


def test_material_win_with_policy_regression_guardrail_keeps_logistic_regression() -> None:
    result = select_runtime_model(
        logistic_regression_test_metrics=_metrics(
            pr_auc=0.5563,
            brier=0.1564,
            log_loss=0.4768,
        ),
        xgboost_test_metrics=_metrics(
            pr_auc=0.5720,
            brier=0.1530,
            log_loss=0.4680,
        ),
        logistic_regression_policy=_policy(1_000_000_000),
        xgboost_policy=_policy(990_000_000),
    )
    assert result.selected_model == RUNTIME_MODEL_LOGISTIC_REGRESSION
    assert "expected_recovered" in result.guardrail_failures
