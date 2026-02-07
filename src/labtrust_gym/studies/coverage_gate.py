"""
Coverage gate: ensure summary_coord.csv has at least one row per required_bench
(method_id, risk_id). Used by external reviewer script. Optional strict mode
(LABTRUST_STRICT_COVERAGE=1) exits 1 when any required_bench cell is missing.
"""

from __future__ import annotations

import csv
from pathlib import Path

from labtrust_gym.policy.coordination import (
    get_required_bench_cells,
    load_method_risk_matrix,
)


def check_summary_coverage(
    summary_csv: Path | str,
    matrix_path: Path | str,
    *,
    strict: bool = False,
) -> bool:
    """
    Check that every required_bench (method_id, risk_id) cell has at least one
    row in summary_coord.csv.

    summary_csv: path to summary/summary_coord.csv.
    matrix_path: path to method_risk_matrix YAML (e.g.
        policy/coordination/method_risk_matrix.v0.1.yaml).
    strict: if True and any required cell is missing, raise SystemExit(1).
        If False, report missing and return False.

    Returns True if all required cells have at least one row; False otherwise.
    """
    summary_path = Path(summary_csv)
    matrix_path_resolved = Path(matrix_path)
    if not matrix_path_resolved.is_absolute():
        matrix_path_resolved = Path.cwd() / matrix_path_resolved
    if not summary_path.is_absolute():
        summary_path = Path.cwd() / summary_path

    if not summary_path.is_file():
        raise FileNotFoundError(f"Summary CSV not found: {summary_path}")
    if not matrix_path_resolved.is_file():
        raise FileNotFoundError(f"Matrix not found: {matrix_path_resolved}")

    matrix = load_method_risk_matrix(matrix_path_resolved)
    required = get_required_bench_cells(matrix)

    summary_pairs: set[tuple[str, str]] = set()
    with summary_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mid = (row.get("method_id") or "").strip()
            rid = (row.get("risk_id") or "").strip()
            if mid or rid:
                summary_pairs.add((mid, rid))

    missing: list[tuple[str, str]] = []
    for cell in required:
        if not isinstance(cell, dict):
            continue
        mid = str(cell.get("method_id") or "").strip()
        rid = str(cell.get("risk_id") or "").strip()
        if (mid, rid) not in summary_pairs:
            missing.append((mid, rid))

    if not missing:
        return True

    for mid, rid in missing:
        print(f"Missing coverage: (method_id={mid!r}, risk_id={rid!r})")
    if strict:
        raise SystemExit(1)
    return False
