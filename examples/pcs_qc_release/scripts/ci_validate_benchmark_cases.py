#!/usr/bin/env python3
"""CI: validate committed BenchmarkCase.v0 suite."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.benchmark_cases import verify_benchmark_cases

BENCHMARK = ROOT / "examples" / "pcs_qc_release" / "benchmark"


def main() -> int:
    if not BENCHMARK.is_dir():
        raise FileNotFoundError(
            f"missing benchmark tree: {BENCHMARK}; run "
            "labtrust generate-benchmark-cases --out examples/pcs_qc_release/benchmark"
        )
    checks = verify_benchmark_cases(BENCHMARK, policy_root=ROOT)
    for label in checks:
        print(f"OK {label}")
    print("benchmark cases CI OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
