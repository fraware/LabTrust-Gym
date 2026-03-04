#!/usr/bin/env python3
"""
Uncertainty report: load a run dir's summary CSV and policy/benchmarks/uncertainty_metric_mapping.v0.1.json,
output epistemic vs aleatoric metric sections and optionally flag metrics missing from the mapping.

Optional --gate <yaml_path>: thresholds per metric (epistemic/aleatoric); exit non-zero if any violated.
Gate YAML shape: thresholds: { epistemic: { metric_key: { min?: float, max?: float } }, aleatoric: { ... } }

Usage:
  python scripts/uncertainty_report.py --run <run_dir> [--policy-root <root>] [--gate <gate.yaml>]
  labtrust uncertainty-report --run <run_dir>

Exit 0 on success; non-zero on missing run dir, invalid mapping, or gate threshold violation.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def _find_summary_csv(run_dir: Path) -> Path | None:
    """Return first summary CSV under run_dir (summary/summary_coord.csv, pack_summary.csv, etc.)."""
    for name in ("summary_coord.csv", "pack_summary.csv", "summary_v0.3.csv"):
        p = run_dir / "summary" / name
        if p.exists():
            return p
        p = run_dir / name
        if p.exists():
            return p
    return None


def _load_mapping(policy_root: Path) -> dict[str, str]:
    """Load mapping from policy/benchmarks/uncertainty_metric_mapping.v0.1.json. Return dict key -> type."""
    path = policy_root / "policy" / "benchmarks" / "uncertainty_metric_mapping.v0.1.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data.get("mapping") or {})


def _load_gate(gate_path: Path) -> dict[str, dict[str, dict[str, float]]]:
    """Load gate YAML: { epistemic: { metric: { min?, max? } }, aleatoric: { ... } }."""
    if not gate_path.exists():
        return {}
    try:
        import yaml

        data = yaml.safe_load(gate_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return dict(data.get("thresholds") or {})


def _check_gate(
    row: dict[str, str],
    gate: dict[str, dict[str, dict[str, float]]],
) -> list[str]:
    """Check first data row against gate thresholds. Return list of violation messages."""
    violations: list[str] = []
    for category in ("epistemic", "aleatoric"):
        metrics_cfg = gate.get(category)
        if not isinstance(metrics_cfg, dict):
            continue
        for metric_key, limits in metrics_cfg.items():
            if not isinstance(limits, dict):
                continue
            raw = row.get(metric_key)
            if raw is None or raw == "":
                continue
            try:
                val = float(raw)
            except (ValueError, TypeError):
                continue
            min_ = limits.get("min")
            max_ = limits.get("max")
            if min_ is not None and val < min_:
                violations.append(f"{category}/{metric_key}: {val} < min {min_}")
            if max_ is not None and val > max_:
                violations.append(f"{category}/{metric_key}: {val} > max {max_}")
    return violations


def run_report(
    run_dir: Path,
    policy_root: Path,
    gate_path: Path | None = None,
) -> tuple[str, int]:
    """
    Build epistemic/aleatoric report. If gate_path is set, check first summary row against thresholds.
    Returns (report_text, exit_code). Exit 1 on gate violation.
    """
    run_dir = Path(run_dir)
    policy_root = Path(policy_root)
    if not run_dir.is_dir():
        return f"Run dir not found: {run_dir}\n", 1
    summary_path = _find_summary_csv(run_dir)
    if not summary_path:
        return f"No summary CSV found under {run_dir}\n", 1
    mapping = _load_mapping(policy_root)
    if not mapping:
        return "Uncertainty mapping not found or empty.\n", 1
    with summary_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return "Summary CSV has no header.\n", 1
        columns = list(reader.fieldnames)
        rows = list(reader)
    epistemic: list[str] = []
    aleatoric: list[str] = []
    unmapped: list[str] = []
    for col in columns:
        t = mapping.get(col)
        if t == "epistemic":
            epistemic.append(col)
        elif t == "aleatoric":
            aleatoric.append(col)
        else:
            unmapped.append(col)
    lines = [
        "# Uncertainty report",
        f"Run dir: {run_dir}",
        f"Summary: {summary_path.name}",
        "",
        "## Epistemic",
        *(epistemic or ["(none in mapping)"]),
        "",
        "## Aleatoric",
        *(aleatoric or ["(none in mapping)"]),
        "",
    ]
    if unmapped:
        lines.append("## Columns not in mapping")
        lines.extend(unmapped[:20])
        if len(unmapped) > 20:
            lines.append(f"... and {len(unmapped) - 20} more")
    exit_code = 0
    if gate_path and gate_path.exists():
        gate = _load_gate(gate_path)
        if gate and rows:
            violations = _check_gate(rows[0], gate)
            if violations:
                lines.append("## Gate violations")
                lines.extend(violations)
                exit_code = 1
    return "\n".join(lines) + "\n", exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Uncertainty report (epistemic/aleatoric from summary + mapping)")
    parser.add_argument("--run", required=True, type=Path, help="Run directory (contains summary/ or summary CSV)")
    parser.add_argument("--policy-root", type=Path, default=None, help="Policy root (default: repo root)")
    parser.add_argument(
        "--gate", type=Path, default=None, help="Optional gate YAML: check thresholds, exit 1 if violated"
    )
    args = parser.parse_args()
    policy_root = args.policy_root
    if policy_root is None:
        try:
            from labtrust_gym.config import get_repo_root

            policy_root = Path(get_repo_root())
        except Exception:
            policy_root = Path(__file__).resolve().parent.parent
    report, code = run_report(args.run, policy_root, gate_path=args.gate)
    print(report, end="")
    return code


if __name__ == "__main__":
    sys.exit(main())
