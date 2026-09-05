"""Run the real recovery engine over the seeded demo cases.

WHY THIS EXISTS

The demo tenant used to ship canned recommendations: a fixed table of round
probabilities (82.0%, 74.0%, 61.0%) labelled `demo-heuristic-v1`, with
`RETRY_SAME_METHOD` hardcoded as rank 1 for every generic case. That produced
three separate problems.

1. **It was not credible.** The case detail said "AI RECOVERY DECISION" over
   numbers no model produced. Only a case someone analysed by hand showed
   `lr-v1.0.0` and real continuous values, so the default path a reviewer sees
   was the least convincing one.

2. **It contradicted the engine's own rules.** Rank 1 was `RETRY_SAME_METHOD`
   regardless of failure category — including `PAYMENT_RAIL_DOWNTIME`, where
   `generate_candidates` would never propose it at all and policy blocks it. The
   seeded data disagreed with the engine that was running beside it.

3. **It was arithmetically wrong.** The canned rows set
   `expected_value_minor = expected_recovered_minor`, never subtracting action
   cost, so "Expected recovery value" and "Expected recovered amount" printed
   the identical number on 94 of 100 cases.

Running the real engine at seed time removes all three at once, and it removes
them at the source rather than by patching each surface. Seeded history is then
built from what the engine actually selected, so the dashboard's action
effectiveness credits the actions RevLoop genuinely performs.

DETERMINISM

The seed is deterministic by design (`DEMO_SEED_VERSION`, `demo_uuid`,
`demo_timestamp`), and analysis must not break that. Two inputs are pinned:

- **Time.** Each case is analysed at its own seeded `analysed_at`, not at
  wall-clock now, so `hours_since_failure` is stable across runs.
- **Rail health.** `compute_analysis` normally reads downtime from the Razorpay
  API. Here it is supplied from the case's own synthetic scenario, so seeding
  makes zero provider calls and does not vary with live rail status.

Everything else — features, model inference, ERV, policy evaluation, ranking and
selection — is the production code path, unmodified.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.enums import FailureCategory
from app.models.recovery_case import RecoveryCase
from app.recovery.schemas import DowntimeContext
from app.recovery.service import AnalysisComputationResult, RecoveryAnalysisService

logger = logging.getLogger(__name__)


class SeedAnalysisError(RuntimeError):
    """Raised when the real engine could not analyse a seeded case."""


@dataclass(frozen=True)
class SeededAnalysis:
    """One case's real analysis, ready to be turned into seed rows."""

    case_id: UUID
    analysis_run_id: UUID
    computation: AnalysisComputationResult
    analysed_at: datetime


def downtime_context_for_case(failure_category: str | None) -> DowntimeContext:
    """The synthetic rail-health context for a seeded case.

    Derived from the case's own failure category so the seeded world is
    self-consistent: a case whose story is "the UPI rail was down" is analysed
    with the rail actually marked degraded, which is what makes policy block
    `RETRY_SAME_METHOD` on it and makes the recommendation legible.

    This is synthetic scenario data, exactly like the seeded error codes it sits
    beside, and the whole tenant is labelled as synthetic. It is not a claim
    about any real outage.
    """
    if failure_category == FailureCategory.PAYMENT_RAIL_DOWNTIME.value:
        return DowntimeContext(
            lookup_status="KNOWN",
            rail_degraded=True,
            severity="high",
            matched_method="upi",
        )
    # Everything else: the lookup ran and found nothing wrong. Deliberately
    # NO_DOWNTIME rather than UNKNOWN, because UNKNOWN marks the provider state
    # uncertain, which suppresses RETRY_SAME_METHOD everywhere and would hide a
    # candidate the engine should genuinely be weighing.
    return DowntimeContext(lookup_status="NO_DOWNTIME", rail_degraded=False, severity="none")


def analyse_seeded_cases(
    session: Session,
    *,
    settings: Settings,
    organization_id: UUID,
    analysis_plan: dict[UUID, tuple[UUID, datetime]],
) -> dict[UUID, SeededAnalysis]:
    """Analyse each planned case with the production engine.

    `analysis_plan` maps case id -> (analysis_run_id, analysed_at), so the run
    ids stay the canonical deterministic ones the seed already publishes.

    Fails closed. A seed that silently fell back to heuristic probabilities
    would reintroduce exactly the credibility gap this module removes, and it
    would do so invisibly -- the rows would still be labelled with whatever
    model version the fallback reported.
    """
    service = RecoveryAnalysisService(
        session,
        settings=settings,
        # No provider client and no factory: downtime is supplied per case
        # below, so nothing here can reach the network.
        razorpay_client=None,
        razorpay_client_factory=None,
        # The seeded dataset must be produced by the real model or not at all.
        allow_model_fallback=False,
    )

    cases = session.execute(
        select(RecoveryCase).where(
            RecoveryCase.organization_id == organization_id,
            RecoveryCase.id.in_(list(analysis_plan)),
        )
    ).scalars().all()

    found = {case.id for case in cases}
    missing = sorted(str(case_id) for case_id in analysis_plan if case_id not in found)
    if missing:
        raise SeedAnalysisError(
            "Cases planned for analysis were not persisted: " + ", ".join(missing)
        )

    results: dict[UUID, SeededAnalysis] = {}
    for case in cases:
        run_id, analysed_at = analysis_plan[case.id]
        try:
            computation = service.compute_analysis(
                case=case,
                analysis_run_id=run_id,
                current_time=analysed_at,
                downtime_override=downtime_context_for_case(case.failure_category),
            )
        except Exception as exc:  # noqa: BLE001 - re-raised as a seed failure
            raise SeedAnalysisError(
                f"Real-model analysis failed for seeded case {case.id}: {exc}"
            ) from exc
        results[case.id] = SeededAnalysis(
            case_id=case.id,
            analysis_run_id=run_id,
            computation=computation,
            analysed_at=analysed_at,
        )

    logger.info("Seed analysis completed for %d cases via the real engine.", len(results))
    return results


__all__ = [
    "SeedAnalysisError",
    "SeededAnalysis",
    "analyse_seeded_cases",
    "downtime_context_for_case",
]
