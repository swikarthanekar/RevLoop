"""Tests for the cached held-out policy simulation.

The cache exists so the evaluation page answers instantly instead of making its
first visitor wait ~10s for a cold dataset regeneration. That is only legitimate
because the evaluation is deterministic: the cached answer is the same answer a
fresh run produces, not a stale approximation of it. These tests assert exactly
that, plus the honesty properties the page depends on -- a visible
`computed_at`, and a recompute that demonstrably re-runs the work.
"""

from __future__ import annotations

import pytest

from app.demo.batch_cache import (
    get_cached_batch,
    peek_cached_batch,
    refresh_cached_batch,
    reset_cache_for_tests,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def test_first_read_computes_and_subsequent_reads_are_cached() -> None:
    assert peek_cached_batch() is None
    first = get_cached_batch()
    assert peek_cached_batch() is not None
    second = get_cached_batch()
    # Identity, not just equality: the second read must not recompute.
    assert first is second


def test_cached_result_carries_its_own_provenance() -> None:
    """A stored number must say when it was produced.

    Without this the page shows a figure with no way to tell a live evaluation
    from a committed fixture, which is precisely the doubt the Proof page has to
    answer.
    """
    cached = get_cached_batch()
    assert cached.computed_at.tzinfo is not None
    assert cached.duration_seconds > 0


def test_recompute_replaces_the_cache_and_moves_the_timestamp() -> None:
    first = get_cached_batch()
    second = refresh_cached_batch()
    assert second is not first
    assert second.computed_at >= first.computed_at
    assert peek_cached_batch() is second


def test_recompute_reproduces_identical_figures() -> None:
    """Determinism is what makes caching honest rather than a shortcut.

    It is also the point of the Recompute control: watching every figure stay
    identical while the timestamp moves is the evidence that the evaluation is
    live and reproducible, not a fixture.
    """
    first = get_cached_batch().result
    second = refresh_cached_batch().result

    assert (
        second.revloop_model_policy.realized_recovery_rate
        == first.revloop_model_policy.realized_recovery_rate
    )
    assert (
        second.naive_baseline_policy.realized_recovery_rate
        == first.naive_baseline_policy.realized_recovery_rate
    )
    assert (
        second.incremental_realized_recovered_minor
        == first.incremental_realized_recovered_minor
    )
    assert second.dataset.seed == first.dataset.seed
    assert second.scorer.model_version == first.scorer.model_version


def test_evaluation_keeps_its_synthetic_labelling() -> None:
    """Caching must not strip the provenance that keeps the claim honest."""
    result = get_cached_batch().result
    assert result.data_source == "SYNTHETIC_SIMULATION"
    assert result.evaluation_label == "SYNTHETIC POLICY SIMULATION"
    assert result.dataset.split == "test"
    assert result.scorer.model_version == "lr-v1.0.0"


def test_revloop_policy_is_compared_against_the_same_cohort() -> None:
    """An uplift is meaningless unless both policies saw the same cases."""
    result = get_cached_batch().result
    assert (
        result.revloop_model_policy.number_of_cases
        == result.naive_baseline_policy.number_of_cases
    )
    assert (
        result.revloop_model_policy.amount_at_risk_minor
        == result.naive_baseline_policy.amount_at_risk_minor
    )
    assert result.revloop_model_policy.number_of_cases == result.dataset.case_count


def test_warm_up_failure_cannot_break_startup() -> None:
    """A warm-up that raises must be swallowed, not propagated."""
    from unittest.mock import patch

    from app.demo.batch_cache import warm_cache_in_background

    with patch(
        "app.demo.batch_cache.run_demo_batch",
        side_effect=RuntimeError("simulated evaluation failure"),
    ):
        thread = warm_cache_in_background()
        thread.join(timeout=10)

    assert not thread.is_alive()
    # Nothing cached, and no exception escaped to the caller.
    assert peek_cached_batch() is None
