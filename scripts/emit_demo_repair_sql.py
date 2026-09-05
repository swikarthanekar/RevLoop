#!/usr/bin/env python3
"""Emit SQL that returns drifted demo cases to their canonical seeded state.

WHEN TO USE THIS

Prefer `POST /api/v1/demo/reset` (DEPLOYMENT.md section 10). Reset rebuilds the
whole tenant from the same canonical spec, preserves hand-provisioned
`user_profiles` rows, and runs in one transaction.

This script exists for the case where reset is not available yet -- the
deployment has not picked up the reset fix, or `DEMO_RESET_ENABLED` cannot be
set right now -- and a specific set of cases has been consumed by rehearsal or
testing. It repairs only the cases you name, and touches nothing else in the
tenant.

WHY IT IS GENERATED RATHER THAN HAND-WRITTEN

Every value it emits is read from `build_demo_seed_spec()`, the same function
the seed itself uses. Hand-typed repair SQL drifts from the seed the first time
the seed changes; this cannot. Re-run it after any seed change and you get SQL
that matches the new canonical state.

USAGE

    # every case whose canonical status is DETECTED
    python scripts/emit_demo_repair_sql.py --status DETECTED

    # specific case ids, whatever their canonical status
    python scripts/emit_demo_repair_sql.py --case-id 56f85566-... --case-id ...

    # write to a file, then review before running it anywhere
    python scripts/emit_demo_repair_sql.py --status DETECTED > repair.sql

The SQL is wrapped in BEGIN/COMMIT and is idempotent: running it twice leaves
the same state, because it assigns canonical values rather than applying
deltas.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "apps" / "api"))

from app.demo.constants import DEMO_ORGANIZATION_ID, demo_uuid  # noqa: E402
from app.demo.factory import RecoveryCaseSpec, build_demo_seed_spec  # noqa: E402


def _sql_literal(value: object) -> str:
    """Render a Python value as a SQL literal.

    Only ever applied to values read out of the canonical seed spec -- UUIDs,
    timestamps, integers, Decimals and None -- never to anything user-supplied,
    so there is no injection surface here. Strings are still escaped.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    return "'" + text.replace("'", "''") + "'"


def _case_repair_statements(case: RecoveryCaseSpec) -> list[str]:
    org = _sql_literal(str(DEMO_ORGANIZATION_ID))
    case_id = _sql_literal(str(case.id))
    seeded_created_audit = _sql_literal(str(demo_uuid(f"audit:{case.id}:created")))

    statements = [
        f"-- {case.id} -> canonical status {case.status}",
        # Child rows first. Anything produced after seeding (an analysis run,
        # an action, an outcome) is not part of the canonical state.
        f"DELETE FROM recovery_outcomes WHERE organization_id = {org} "
        f"AND case_id = {case_id};",
        f"DELETE FROM recovery_actions WHERE organization_id = {org} "
        f"AND case_id = {case_id};",
        f"DELETE FROM recovery_recommendations WHERE organization_id = {org} "
        f"AND case_id = {case_id};",
        # Keep the one audit row the seed itself wrote; drop everything the
        # workflow appended afterwards.
        f"DELETE FROM audit_logs WHERE organization_id = {org} "
        f"AND case_id = {case_id} AND id <> {seeded_created_audit};",
        # Then the case row itself, assigned (not adjusted) to canonical values.
        f"UPDATE recovery_cases SET\n"
        f"    status = {_sql_literal(case.status)},\n"
        f"    current_analysis_run_id = {_sql_literal(case.current_analysis_run_id)},\n"
        f"    recovery_probability = {_sql_literal(case.recovery_probability)},\n"
        f"    expected_recoverable_minor = "
        f"{_sql_literal(case.expected_recoverable_minor)},\n"
        f"    priority_score = {_sql_literal(case.priority_score)},\n"
        f"    version = {_sql_literal(case.version)},\n"
        f"    opened_at = {_sql_literal(case.opened_at)},\n"
        f"    last_transition_at = {_sql_literal(case.last_transition_at)},\n"
        f"    resolved_at = {_sql_literal(case.resolved_at)},\n"
        f"    updated_at = {_sql_literal(case.updated_at)}\n"
        f"WHERE organization_id = {org} AND id = {case_id};",
        "",
    ]
    return statements


def _select_cases(
    cases: Iterable[RecoveryCaseSpec],
    *,
    status: str | None,
    case_ids: list[str],
) -> list[RecoveryCaseSpec]:
    if case_ids:
        wanted = {value.lower() for value in case_ids}
        selected = [case for case in cases if str(case.id).lower() in wanted]
        found = {str(case.id).lower() for case in selected}
        missing = sorted(wanted - found)
        if missing:
            raise SystemExit(
                "These case ids are not part of the canonical demo seed: "
                + ", ".join(missing)
            )
        return selected
    if status:
        return [case for case in cases if case.status == status]
    raise SystemExit("Pass --status or at least one --case-id.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status",
        help="Repair every case whose CANONICAL status is this (e.g. DETECTED).",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        dest="case_ids",
        help="Repair this specific case id. Repeatable.",
    )
    args = parser.parse_args()

    spec = build_demo_seed_spec()
    selected = _select_cases(
        spec.recovery_cases, status=args.status, case_ids=args.case_ids
    )

    print("-- RevLoop demo repair SQL")
    print("-- Generated by scripts/emit_demo_repair_sql.py from the canonical seed.")
    print(f"-- Organization: {DEMO_ORGANIZATION_ID}")
    print(f"-- Cases repaired: {len(selected)}")
    print("--")
    print("-- Review before running. Prefer POST /api/v1/demo/reset where available.")
    print("-- Safe to run more than once: it assigns canonical values, not deltas.")
    print()
    print("BEGIN;")
    print()
    for case in selected:
        for line in _case_repair_statements(case):
            print(line)
    print("-- Verify before committing. Expect the canonical distribution.")
    print("SELECT status, COUNT(*) FROM recovery_cases")
    print(f"WHERE organization_id = {_sql_literal(str(DEMO_ORGANIZATION_ID))}")
    print("GROUP BY status ORDER BY status;")
    print()
    print("COMMIT;")


if __name__ == "__main__":
    main()
