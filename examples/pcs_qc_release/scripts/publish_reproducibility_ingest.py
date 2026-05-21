#!/usr/bin/env python3
"""Publish LabTrust reproducibility pcs_bench_ingest.v0.json for pcs-bench consumption."""

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
from labtrust_gym.pcs.benchmark_pcs_bench_ingest import PCS_BENCH_INGEST_NAME
from labtrust_gym.pcs.benchmark_reproducibility import (
    BENCHMARK_MANIFEST_NAME,
    BENCHMARK_REPORT_NAME,
    BENCHMARK_RUN_NAME,
    COVERAGE_REPORT_NAME,
    benchmark_reproducibility,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "benchmark_runs" / "labtrust_reproducibility",
        help="LabTrust reproducibility output directory",
    )
    parser.add_argument(
        "--pcs-bench-runs",
        type=Path,
        default=None,
        help="pcs-bench ingest destination (default: ../pcs-bench/runs/labtrust_reproducibility)",
    )
    parser.add_argument(
        "--pcs-core",
        type=Path,
        default=ROOT.parent / "pcs-core",
        help="pcs-core root for validation",
    )
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--mode",
        choices=("hash_stability", "full_regeneration"),
        default="hash_stability",
    )
    args = parser.parse_args()

    out = args.out.resolve()
    pcs_core = resolve_pcs_core_schema_root(args.pcs_core)
    release = ROOT / "examples" / "pcs_qc_release" / "release"

    benchmark_reproducibility(
        out,
        workflow_key="hospital_lab.qc_release",
        policy_root=ROOT,
        release_dir=release,
        pcs_core=pcs_core,
        runs=args.runs,
        seed=42,
        mode=args.mode,
        include_hash_stability=args.mode == "full_regeneration",
        validate_pcs_core_output=pcs_core,
    )
    validate_pcs_core_reproducibility_outputs(
        out, pcs_core_root=pcs_core or args.pcs_core.resolve(), policy_root=ROOT
    )

    dest_root = (
        args.pcs_bench_runs.resolve()
        if args.pcs_bench_runs
        else (ROOT.parent / "pcs-bench" / "runs" / "labtrust_reproducibility").resolve()
    )
    dest_root.mkdir(parents=True, exist_ok=True)
    for name in (
        PCS_BENCH_INGEST_NAME,
        BENCHMARK_MANIFEST_NAME,
        BENCHMARK_REPORT_NAME,
        BENCHMARK_RUN_NAME,
        COVERAGE_REPORT_NAME,
    ):
        src = out / name
        if src.is_file():
            shutil.copy2(src, dest_root / name)

    print(f"published reproducibility ingest to {dest_root}")
    print(f"  ingest: {dest_root / PCS_BENCH_INGEST_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
