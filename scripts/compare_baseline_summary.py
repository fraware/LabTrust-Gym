#!/usr/bin/env python3
"""
Compare two summary CSV files (e.g. published baseline vs local run).

Usage:
  python scripts/compare_baseline_summary.py <baseline_summary.csv> <local_summary.csv> [--tolerance 1e-6]

Accepts summary_v0.2.csv (CI parity) or summary_v0.3.csv (paper-grade). Compares the same
metric set as the baseline regression guard: task, agent_baseline_id, n_episodes, and
exact-integer metrics (throughput_mean, holds_count_mean, tokens_minted_mean,
tokens_consumed_mean, steps_mean). Optional --tolerance for float columns (human review only).
Exits 0 if key columns match; exits 1 and prints differences otherwise.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Summary columns to compare; aligned with test_official_baselines_regression EXACT_METRIC_KEYS
# (throughput, holds_count, tokens_minted, tokens_consumed, steps) as *_mean, plus identifiers.
KEY_COLS = ["task", "agent_baseline_id"]
SUMMARY_METRIC_COLS = [
    "n_episodes",
    "throughput_mean",
    "holds_count_mean",
    "tokens_minted_mean",
    "tokens_consumed_mean",
    "steps_mean",
]


def load_summary(path: Path) -> list[dict[str, str]]:
    """Load summary CSV into list of row dicts."""
    rows: list[dict[str, str]] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare baseline summary CSV to local summary CSV (v0.2 or v0.3)."
    )
    parser.add_argument(
        "baseline_csv",
        type=Path,
        help="Path to baseline summary (e.g. benchmarks/baselines_official/v0.2/summary_v0.2.csv)",
    )
    parser.add_argument(
        "local_csv",
        type=Path,
        help="Path to local summary CSV",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        metavar="T",
        help="Optional tolerance for float comparison (e.g. 1e-6). Omit for exact match.",
    )
    args = parser.parse_args()

    base_path = args.baseline_csv
    local_path = args.local_csv
    tolerance = args.tolerance

    if not base_path.exists():
        print(f"Baseline file not found: {base_path}", file=sys.stderr)
        return 1
    if not local_path.exists():
        print(f"Local file not found: {local_path}", file=sys.stderr)
        return 1

    base_rows = load_summary(base_path)
    local_rows = load_summary(local_path)

    compare_cols = KEY_COLS + [
        c
        for c in SUMMARY_METRIC_COLS
        if base_rows and c in (base_rows[0] or {})
        and local_rows
        and c in (local_rows[0] or {})
    ]

    if len(base_rows) != len(local_rows):
        print(
            f"Row count: baseline={len(base_rows)}, local={len(local_rows)}",
            file=sys.stderr,
        )
        return 1

    diffs: list[str] = []
    for i, (br, lr) in enumerate(zip(base_rows, local_rows)):
        for col in compare_cols:
            bv = br.get(col, "")
            lv = lr.get(col, "")
            if bv == lv:
                continue
            if tolerance is not None and col != "task" and col != "agent_baseline_id":
                try:
                    bf = float(bv)
                    lf = float(lv)
                    if abs(bf - lf) <= tolerance:
                        continue
                except (ValueError, TypeError):
                    pass
            else:
                try:
                    if float(bv) == float(lv):
                        continue
                except (ValueError, TypeError):
                    pass
            diffs.append(f"  row {i+1} {col}: baseline={bv!r} local={lv!r}")

    if diffs:
        print("Differences:", file=sys.stderr)
        for d in diffs:
            print(d, file=sys.stderr)
        return 1
    print("Match: summary key columns agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
