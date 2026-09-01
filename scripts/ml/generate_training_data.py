#!/usr/bin/env python3
"""Generate deterministic synthetic action-level recovery ML dataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _configure_import_paths() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    api_root = repo_root / "apps" / "api"
    scripts_root = repo_root / "scripts"
    for path in (str(api_root), str(scripts_root)):
        if path not in sys.path:
            sys.path.insert(0, path)
    return repo_root


def main(argv: list[str] | None = None) -> int:
    repo_root = _configure_import_paths()

    from ml.common import (
        DATASET_VERSION,
        DEFAULT_CASE_COUNT,
        DEFAULT_SEED,
        generate_dataset,
        write_dataset,
    )

    parser = argparse.ArgumentParser(
        description="Generate synthetic action-level recovery ML dataset.",
    )
    parser.add_argument(
        "--cases",
        type=int,
        default=DEFAULT_CASE_COUNT,
        help=f"Number of synthetic cases (default: {DEFAULT_CASE_COUNT}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Deterministic generation seed (default: {DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--split-seed",
        type=int,
        default=None,
        help="Optional separate seed for case split assignment.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "data" / "synthetic" / "generated",
        help="Directory for training_data.csv and summary.json.",
    )
    parser.add_argument(
        "--dataset-version",
        type=str,
        default=DATASET_VERSION,
        help=f"Dataset generator version label (default: {DATASET_VERSION}).",
    )
    args = parser.parse_args(argv)

    if args.cases <= 0:
        parser.error("--cases must be > 0")
    if args.seed < 0:
        parser.error("--seed must be non-negative")

    dataset = generate_dataset(
        case_count=args.cases,
        seed=args.seed,
        split_seed=args.split_seed,
        dataset_version=args.dataset_version,
    )
    csv_path, summary_path = write_dataset(args.output_dir, dataset)

    summary = dataset.summary
    print(f"Wrote {csv_path}")
    print(f"Wrote {summary_path}")
    print(f"cases={summary['case_count']} rows={summary['row_count']}")
    print(f"split_case_counts={summary['split_case_counts']}")
    print(f"split_row_counts={summary['split_row_counts']}")
    print(f"overall_positive_label_rate={summary['overall_positive_label_rate']:.4f}")
    print(f"action_type_distribution={summary['action_type_distribution']}")
    print(f"failure_category_distribution={summary['failure_category_distribution']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
