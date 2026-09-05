#!/usr/bin/env python3
"""Decide whether to turn the Gemini explanation path on, using evidence.

WHY THIS EXISTS

Setting `GEMINI_API_KEY` does not, on its own, mean explanations become
LLM-generated. `RecommendationExplanationService.enrich` validates every model
response against a server-side allowlist (`app/ai/validation.py`): any percent
or money token the LLM writes must match an approved token exactly. That
allowlist is the reason the LLM cannot invent a number -- it is a feature, not
an obstacle -- but it also means a model that rounds "78.2%" to "78%", or
writes "Rs 1,533" where the approved phrase is "₹1,533.07", fails validation and
silently falls back to the template.

The failure is invisible from outside: the response still contains a perfectly
good explanation, just with `explanation_source: TEMPLATE_FALLBACK`. So the
deployment would carry the latency cost of a live LLM call on every analyze and
show none of the benefit, and nobody would notice.

This script measures the two numbers that actually decide it:

  1. What fraction of real cases come back as LLM rather than TEMPLATE_FALLBACK.
  2. What the call costs in latency, which lands on the analyze request path.

THE KEY NEVER NEEDS TO LEAVE YOUR MACHINE

Read from the environment, never printed, never written to a file. Run:

    export GEMINI_API_KEY='...'          # not committed, not echoed
    export REVLOOP_TEST_DATABASE_URL='postgresql+psycopg://...'
    apps/api/.venv/bin/python scripts/check_llm_explanations.py --samples 10

Seed the database first if it is empty:

    apps/api/.venv/bin/python -c \\
      "from app.demo.seed import seed_demo_database; seed_demo_database(reset=True)"

Runs entirely against the local demo tenant. Read-only: it calls `enrich`,
which performs no writes.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "apps" / "api"))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.ai.explanations import RecommendationExplanationService  # noqa: E402
from app.ai.factory import gemini_api_key_configured  # noqa: E402
from app.core.config import Settings, normalize_database_url  # noqa: E402
from app.demo.constants import DEMO_ORGANIZATION_ID  # noqa: E402
from app.models.recovery_case import RecoveryCase  # noqa: E402


def _database_url() -> str:
    url = os.environ.get("REVLOOP_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit(
            "Set REVLOOP_TEST_DATABASE_URL (preferred) or DATABASE_URL to a local "
            "database holding the seeded demo tenant."
        )
    return normalize_database_url(url)



def _debug_one_call(session_factory, settings, service) -> None:
    """Show precisely where a single response fails.

    `invalid_response` is raised for three different reasons -- empty text,
    unparseable JSON, or a schema mismatch -- and they call for completely
    different fixes. This separates them instead of guessing.
    """
    import asyncio
    import json as _json

    from app.ai.gemini_provider import GeminiLLMProvider
    from app.ai.schemas import RecommendationExplanation

    with session_factory() as session:
        case = session.execute(
            select(RecoveryCase)
            .where(
                RecoveryCase.organization_id == DEMO_ORGANIZATION_ID,
                RecoveryCase.current_analysis_run_id.is_not(None),
            )
            .limit(1)
        ).scalars().one()
        input_data = service._build_input(
            session,
            case_id=case.id,
            organization_id=DEMO_ORGANIZATION_ID,
            analysis_run_id=case.current_analysis_run_id,
        )

    provider = GeminiLLMProvider(settings=settings)

    async def raw() -> str | None:
        from google.genai import types

        client = provider._resolve_client()
        payload = {
            "task": "recommendation_explanation",
            "approved_facts": input_data.model_dump(mode="json"),
        }
        config = types.GenerateContentConfig(
            system_instruction=provider.__class__.__module__ and __import__(
                "app.ai.gemini_provider", fromlist=["SYSTEM_INSTRUCTION"]
            ).SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_json_schema=RecommendationExplanation.model_json_schema(),
        )
        response = await client.aio.models.generate_content(
            model=provider.model_name,
            contents=_json.dumps(payload, ensure_ascii=True),
            config=config,
        )
        return getattr(response, "text", None)

    print("STEP 1 — raw call")
    try:
        text = asyncio.run(raw())
    except Exception as exc:  # noqa: BLE001 - diagnostic
        print(f"  the API call itself failed: {type(exc).__name__}: {exc}")
        return
    if not text:
        print("  FAIL: the model returned empty text.")
        print("  -> the schema or system instruction is likely being rejected.")
        return
    print(f"  OK: {len(text)} chars returned")
    print("  ---- raw text ----")
    print("  " + text.strip().replace("\n", "\n  ")[:1200])
    print("  ------------------")

    print("STEP 2 — JSON parse")
    try:
        parsed = _json.loads(text)
    except Exception as exc:  # noqa: BLE001 - diagnostic
        print(f"  FAIL: not valid JSON: {exc}")
        print("  -> response_mime_type is not being honoured.")
        return
    print(f"  OK: parsed. top-level keys = {sorted(parsed) if isinstance(parsed, dict) else type(parsed).__name__}")

    print("STEP 3 — schema validation")
    try:
        RecommendationExplanation.model_validate(parsed)
    except Exception as exc:  # noqa: BLE001 - diagnostic
        print(f"  FAIL: {type(exc).__name__}")
        print(f"  {exc}")
        expected = set(RecommendationExplanation.model_json_schema()["properties"])
        if isinstance(parsed, dict):
            extra = sorted(set(parsed) - expected)
            missing = sorted(expected - set(parsed))
            if extra:
                print(f"  -> unexpected keys (extra='forbid' rejects these): {extra}")
            if missing:
                print(f"  -> missing keys: {missing}")
        return
    print("  OK: the response satisfies the schema.")
    print()
    print("All three steps passed, so invalid_response is intermittent rather")
    print("than structural. Re-run the non-debug mode with more samples.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--samples", type=int, default=10, help="How many analysed cases to try."
    )
    parser.add_argument(
        "--show", type=int, default=1, help="How many explanations to print in full."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "Make one raw call and show exactly which step failed: the model's "
            "own text, then JSON parsing, then schema validation. Use this when "
            "the run reports invalid_response, which means the response failed "
            "OUR parse rather than the content allowlist."
        ),
    )
    args = parser.parse_args()

    url = _database_url()
    settings = Settings(app_env="test", demo_mode=True, database_url=url, _env_file=None)

    if not gemini_api_key_configured(settings):
        raise SystemExit(
            "GEMINI_API_KEY is unset, blank, or a dev-/test-/placeholder- value.\n"
            "Every explanation would be TEMPLATE_FALLBACK, which is what you "
            "already have. Export a real key and re-run."
        )

    # Confirm a key is in play without ever revealing it.
    secret = settings.gemini_api_key.get_secret_value().strip()
    print(f"key: present, {len(secret)} chars (never printed or logged)")
    print(f"model: {settings.gemini_model_name}")
    print(f"timeout: {settings.gemini_timeout_seconds}s, no retries")
    print()

    engine = create_engine(url, future=True)
    session_factory = sessionmaker(bind=engine, future=True)
    service = RecommendationExplanationService(settings=settings)

    if args.debug:
        _debug_one_call(session_factory, settings, service)
        return

    sources: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    latencies: list[float] = []
    shown = 0

    with session_factory() as session:
        cases = list(
            session.execute(
                select(RecoveryCase)
                .where(
                    RecoveryCase.organization_id == DEMO_ORGANIZATION_ID,
                    RecoveryCase.current_analysis_run_id.is_not(None),
                )
                .limit(args.samples)
            ).scalars()
        )
        if not cases:
            raise SystemExit(
                "No analysed cases in the demo tenant. Seed the database first "
                "(see the docstring at the top of this file)."
            )

        for case in cases:
            started = time.perf_counter()
            try:
                result = service.enrich(
                    session,
                    case_id=case.id,
                    organization_id=DEMO_ORGANIZATION_ID,
                    analysis_run_id=case.current_analysis_run_id,
                )
            except Exception as exc:  # noqa: BLE001 - this is a diagnostic
                elapsed = time.perf_counter() - started
                latencies.append(elapsed)
                sources["RAISED"] += 1
                failures[type(exc).__name__] += 1
                print(f"  {case.id}  RAISED {type(exc).__name__}  {elapsed:.2f}s")
                continue

            elapsed = time.perf_counter() - started
            latencies.append(elapsed)
            sources[result.explanation_source] += 1
            if result.failure_category:
                failures[result.failure_category] += 1

            marker = "LLM " if result.explanation_source == "LLM" else "tmpl"
            reason = f"  ({result.failure_category})" if result.failure_category else ""
            print(f"  {case.id}  {marker}  {elapsed:5.2f}s{reason}")

            if shown < args.show:
                shown += 1
                print(f"    summary : {result.explanation.summary}")
                for item in result.explanation.evidence:
                    print(f"    evidence: {item}")
                for item in result.explanation.safety:
                    print(f"    safety  : {item}")

    total = sum(sources.values())
    llm = sources.get("LLM", 0)
    print()
    print("=" * 68)
    print(f"cases tried            : {total}")
    print(f"LLM-generated          : {llm} ({llm / total:.0%})" if total else "")
    print(f"fell back to template  : {sources.get('TEMPLATE_FALLBACK', 0)}")
    if sources.get("RAISED"):
        print(f"raised                 : {sources['RAISED']}")
    if failures:
        print(f"fallback reasons       : {dict(failures)}")
    if latencies:
        latencies.sort()
        p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)]
        print(
            f"latency                : median {statistics.median(latencies):.2f}s, "
            f"p95 {p95:.2f}s, max {max(latencies):.2f}s"
        )
    print("=" * 68)
    print()

    # The recommendation, stated plainly, from the numbers just measured.
    if not total:
        return
    rate = llm / total
    if rate >= 0.8:
        print("VERDICT: enable it. The LLM path succeeds on most cases, so the")
        print("latency buys a real, visible capability.")
    elif rate >= 0.4:
        print("VERDICT: marginal. Roughly half of explanations still fall back,")
        print("so you would pay the latency on every analyze for a benefit a")
        print("reviewer sees only half the time. Check the fallback reasons above:")
        print("if they are validation failures, the model is rephrasing approved")
        print("numbers. Worth a prompt tweak before enabling in production.")
    else:
        print("VERDICT: do not enable. Almost everything falls back to the")
        print("template, so the deployment would pay live-LLM latency on every")
        print("analyze and show none of the benefit. Keep TEMPLATE_FALLBACK and")
        print("describe the explanations as deterministic templates -- which is")
        print("accurate, and is a defensible design choice in its own right.")


if __name__ == "__main__":
    main()
