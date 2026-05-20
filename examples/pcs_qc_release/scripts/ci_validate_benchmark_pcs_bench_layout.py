#!/usr/bin/env python3
"""CI: generate and validate pcs-bench layout (no committed tree required)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.benchmark_cases import verify_benchmark_cases
from labtrust_gym.pcs.benchmark_pcs_bench import (
    PCS_BENCH_SUITE_ID,
    generate_benchmark_cases_pcs_bench,
    is_pcs_bench_layout,
)


def main() -> int:
    release = ROOT / "examples" / "pcs_qc_release" / "release"
    pcs_core = ROOT.parent / "pcs-core"
    if not pcs_core.is_dir():
        pcs_core = None

    with tempfile.TemporaryDirectory(prefix="labtrust_pcs_bench_") as tmp:
        out = Path(tmp)
        result = generate_benchmark_cases_pcs_bench(
            out,
            workflow_key="hospital_lab.qc_release",
            policy_root=ROOT,
            release_dir=release,
            seed=42,
            suite_id=PCS_BENCH_SUITE_ID,
            suite_fixture_root="benchmarks/labtrust-qc-release",
        )
        if not is_pcs_bench_layout(out):
            raise RuntimeError("pcs-bench layout generation failed")
        if len(result["valid_cases"]) != 1 or len(result["invalid_cases"]) != 12:
            raise RuntimeError(
                f"expected 1 valid and 12 invalid cases, got "
                f"{len(result['valid_cases'])} valid and {len(result['invalid_cases'])} invalid"
            )
        checks = verify_benchmark_cases(out, policy_root=ROOT, pcs_core_root=pcs_core)
        for label in checks:
            print(f"OK {label}")
        print(
            f"benchmark pcs-bench layout CI OK "
            f"({len(result['valid_cases'])} valid, {len(result['invalid_cases'])} invalid)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
