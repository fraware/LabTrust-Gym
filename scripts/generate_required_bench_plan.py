#!/usr/bin/env python3
"""
Generate policy/risks/required_bench_plan.v0.1.yaml from method_risk_matrix and risk_to_injection_map.
One entry per required_bench cell; evidence.kind = coord_risk with injection_id and cmd template.
Run from repo root.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Implemented injection IDs (in INJECTION_REGISTRY, not NoOp)
IMPLEMENTED_INJECTIONS = frozenset({
    "INJ-DOS-PLANNER-001", "INJ-COMMS-POISON-001", "INJ-ID-SPOOF-001", "INJ-COLLUSION-001",
    "INJ-MEMORY-POISON-001", "INJ-TOOL-MISPARAM-001", "INJ-LLM-PROMPT-INJECT-COORD-001",
    "INJ-COORD-PROMPT-INJECT-001", "inj_msg_poison", "inj_device_fail", "INJ-BID-SPOOF-001",
    "INJ-COMMS-DELAY-001", "INJ-COMMS-DROP-001", "INJ-REPLAY-001", "INJ-COORD-PLAN-REPLAY-001",
    "INJ-COORD-BID-SHILL-001", "INJ-CONSENSUS-POISON-001", "INJ-BLAME-SHIFT-001", "INJ-PARTIAL-OBS-001",
    "INJ-TIMING-QUEUE-001", "INJ-NET-PARTITION-001", "INJ-NET-REORDER-001", "INJ-NET-DROP-SPIKE-001",
    "INJ-CLOCK-SKEW-001", "INJ-TOOL-MISPARAM-001", "INJ-SLOW-POISON-001", "INJ-MEMORY-POISON-COORD-001",
    "inj_poison_obs",
})


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    matrix_path = repo / "policy" / "coordination" / "method_risk_matrix.v0.1.yaml"
    risk_map_path = repo / "policy" / "coordination" / "risk_to_injection_map.v0.1.yaml"
    out_path = repo / "policy" / "risks" / "required_bench_plan.v0.1.yaml"

    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8")) or {}
    risk_map_data = yaml.safe_load(risk_map_path.read_text(encoding="utf-8")) or {}
    cells = (matrix.get("method_risk_matrix") or {}).get("cells") or []
    required = [
        (c["method_id"], c["risk_id"])
        for c in cells
        if isinstance(c, dict) and c.get("required_bench") is True
    ]

    risk_to_inj: dict[str, list[str]] = {}
    for m in risk_map_data.get("mappings") or []:
        rid = m.get("risk_id")
        if rid:
            risk_to_inj[rid] = list(m.get("injection_ids") or [])

    plan_cells: list[dict] = []
    for method_id, risk_id in required:
        inj_list = risk_to_inj.get(risk_id, [])
        injection_id = next((i for i in inj_list if i in IMPLEMENTED_INJECTIONS), inj_list[0] if inj_list else "INJ-COMMS-POISON-001")
        cmd = (
            f'labtrust run-benchmark --task coord_risk --coord-method {method_id} '
            f'--injection {injection_id} --scale small_smoke --episodes 1 --seed 42'
        )
        plan_cells.append({
            "method_id": method_id,
            "risk_id": risk_id,
            "evidence": {
                "kind": "coord_risk",
                "injection_id": injection_id,
                "cmd": cmd,
            },
        })

    out = {"version": "v0.1", "description": "Maps each required_bench (method_id, risk_id) to one evidence action.", "cells": plan_cells}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("# Required-bench plan v0.1: one entry per required_bench cell from method_risk_matrix.\n")
        f.write("# Evidence: coord_risk = run-benchmark coord_risk with method + injection; executor deduplicates runs.\n")
        yaml.dump(out, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"Wrote {len(plan_cells)} cells to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
