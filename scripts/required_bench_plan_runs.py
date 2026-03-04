#!/usr/bin/env python3
"""
Print distinct runs from required_bench_plan and method_risk_matrix.
Output: one line per run: kind method_id injection_id [out_suffix]
or kind security_suite (no method/injection).
Used by run_required_bench_matrix.sh/.ps1 to execute minimal set.
Exit 1 if any required_bench cell has no plan entry.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    matrix_path = repo / "policy" / "coordination" / "method_risk_matrix.v0.1.yaml"
    plan_path = repo / "policy" / "risks" / "required_bench_plan.v0.1.yaml"

    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8")) or {}
    plan_data = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    cells = (matrix.get("method_risk_matrix") or {}).get("cells") or []
    required = {
        (c["method_id"], c["risk_id"]) for c in cells if isinstance(c, dict) and c.get("required_bench") is True
    }
    plan_cells = plan_data.get("cells") or []
    plan_keys = {(c["method_id"], c["risk_id"]) for c in plan_cells if isinstance(c, dict)}

    missing = required - plan_keys
    if missing:
        print("Missing plan entries for required_bench cells:", file=sys.stderr)
        for m, r in sorted(missing):
            print(f"  {m} / {r}", file=sys.stderr)
        return 1

    seen: set[tuple[str, ...]] = set()
    for c in plan_cells:
        if not isinstance(c, dict):
            continue
        ev = c.get("evidence") or {}
        kind = ev.get("kind", "coord_risk")
        if kind == "security_suite":
            key = ("security_suite",)
            if key not in seen:
                seen.add(key)
                print("security_suite")
        else:
            method_id = c.get("method_id", "")
            injection_id = ev.get("injection_id", "")
            key = ("coord_risk", method_id, injection_id)
            if key not in seen:
                seen.add(key)
                suffix = f"{method_id}_{injection_id}".replace("-", "_").replace(".", "_")
                print(f"coord_risk {method_id} {injection_id} {suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
