#!/usr/bin/env python3
"""CLI entrypoint for deterministic RevLoop demo seeding."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.demo.seed import SeedError, seed_demo_database
from app.demo.summary import format_summary_text, summary_from_database


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed deterministic RevLoop demo data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing demo tenant data and recreate the seed deterministically.",
    )
    args = parser.parse_args()

    try:
        result = seed_demo_database(reset=args.reset)
    except SeedError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    session_factory = get_session_factory(get_settings())
    with session_factory() as session:
        summary = summary_from_database(session)

    if result.already_exists:
        print("Demo seed already exists; no changes made.")
    elif result.reset_performed:
        print("Demo tenant reset and reseed completed.")
    else:
        print("Demo seed created.")

    print()
    print(format_summary_text(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
