#!/usr/bin/env python3
"""CI: cross-validate benchmark cases against pcs-core BenchmarkCase.v0 schema."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.benchmark_cases import verify_benchmark_cases


def _resolve_pcs_core() -> Path | None:
    for candidate in (
        ROOT / "pcs-core",
        ROOT.parent / "pcs-core",
    ):
        schema = candidate / "schemas" / "BenchmarkCase.v0.schema.json"
        if schema.is_file():
            return candidate
    return None


def main() -> int:
    pcs_core = _resolve_pcs_core()
    if pcs_core is None:
        print("skip pcs-core BenchmarkCase cross-validation (no checkout)")
        return 0
    benchmark = ROOT / "examples" / "pcs_qc_release" / "benchmark"
    checks = verify_benchmark_cases(benchmark, policy_root=ROOT, pcs_core_root=pcs_core)
    for label in checks:
        print(f"OK {label}")
    print(f"benchmark pcs-core schema OK ({pcs_core})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
