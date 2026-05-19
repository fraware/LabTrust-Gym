#!/usr/bin/env python3
"""Validate BenchmarkCase.v0 suite (same checks as CI)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.benchmark_cases import verify_benchmark_cases

GALLERY = ROOT / "examples" / "pcs_qc_release" / "benchmark"


def main() -> int:
    checks = verify_benchmark_cases(GALLERY, policy_root=ROOT)
    for label in checks:
        print(f"OK {label}")
    print("benchmark validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
