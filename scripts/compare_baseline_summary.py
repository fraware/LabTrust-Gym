#!/usr/bin/env python3
"""
Compare two summary CSV files (e.g. published baseline vs local run).

Usage:
  python scripts/compare_baseline_summary.py <baseline_summary.csv> <local_summary.csv>

Exits 0 if key columns match (task, agent_baseline_id, throughput_mean, violations_total_mean);
exits 1 and prints differences otherwise.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path


def load_summary(path: Path) -> list[dict[str, str]]:
    """Load summary CSV into list of row dicts."""
    rows: list[dict[str, str]] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: compare_baseline_summary.py <baseline_summary.csv> <local_summary.csv>", file=sys.stderr)
        return 2
    base_path = Path(sys.argv[1])
    local_path = Path(sys.argv[2])
    if not base_path.exists():
        print(f"Baseline file not found: {base_path}", file=sys.stderr)
        return 1
    if not local_path.exists():
        print(f"Local file not found: {local_path}", file=sys.stderr)
        return 1

    base_rows = load_summary(base_path)
    local_rows = load_summary(local_path)

    key_cols = ["task", "agent_baseline_id"]
    metric_cols = ["throughput_mean", "violations_total_mean", "n_episodes"]
    compare_cols = key_cols + [c for c in metric_cols if base_rows and c in (base_rows[0] or {})]

    if len(base_rows) != len(local_rows):
        print(f"Row count: baseline={len(base_rows)}, local={len(local_rows)}", file=sys.stderr)
        return 1

    diffs: list[str] = []
    for i, (br, lr) in enumerate(zip(base_rows, local_rows)):
        for col in compare_cols:
            bv = br.get(col, "")
            lv = lr.get(col, "")
            if bv != lv:
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
