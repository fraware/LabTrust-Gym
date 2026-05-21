#!/usr/bin/env python3
"""Materialize golden reproducibility ingest under examples/pcs_qc_release/benchmark_ingest/."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.bench_schemas import (
    resolve_pcs_core_schema_root,
    validate_pcs_core_reproducibility_outputs,
)
from labtrust_gym.pcs.benchmark_reproducibility import benchmark_reproducibility

GOLDEN = ROOT / "examples" / "pcs_qc_release" / "benchmark_ingest" / "golden"
RELEASE = ROOT / "examples" / "pcs_qc_release" / "release"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pcs-core",
        type=Path,
        default=ROOT.parent / "pcs-core",
        help="pcs-core root for validation",
    )
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args()

    pcs_core = resolve_pcs_core_schema_root(args.pcs_core)
    if pcs_core is None:
        raise SystemExit(f"pcs-core schemas not found at {args.pcs_core}")

    if GOLDEN.exists():
        shutil.rmtree(GOLDEN)
    GOLDEN.mkdir(parents=True)

    benchmark_reproducibility(
        GOLDEN,
        workflow_key="hospital_lab.qc_release",
        policy_root=ROOT,
        release_dir=RELEASE,
        pcs_core=pcs_core,
        runs=args.runs,
        seed=42,
        mode="hash_stability",
        include_hash_stability=False,
        validate_pcs_core_output=pcs_core,
    )
    checks = validate_pcs_core_reproducibility_outputs(
        GOLDEN, pcs_core_root=pcs_core, policy_root=ROOT
    )
    print(f"golden reproducibility ingest at {GOLDEN}")
    for label in checks:
        print(f"  OK {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
