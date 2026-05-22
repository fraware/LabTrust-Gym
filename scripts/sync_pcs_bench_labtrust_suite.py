#!/usr/bin/env python3
"""Regenerate LabTrust pcs-bench case suite and copy into sibling pcs-bench benchmarks tree."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcs-core", type=Path, default=root.parent / "pcs-core")
    parser.add_argument(
        "--pcs-bench-out",
        type=Path,
        default=root.parent / "pcs-bench" / "benchmarks" / "labtrust_qc_release",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--validate-pcs-bench", action="store_true", default=True)
    args = parser.parse_args(argv)

    pcs_core = args.pcs_core.resolve()
    out = args.pcs_bench_out.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "labtrust",
        "generate-benchmark-cases",
        "--workflow",
        "hospital_lab.qc_release",
        "--out",
        str(out),
        "--pcs-bench-layout",
        "--seed",
        str(args.seed),
        "--validate-pcs-core-output",
        str(pcs_core),
    ]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=root, check=True)

    verify_cmd = [
        "labtrust",
        "verify-benchmark-cases",
        "--benchmark-dir",
        str(out),
        "--validate-pcs-core-output",
        str(pcs_core),
    ]
    print(" ".join(verify_cmd), flush=True)
    subprocess.run(verify_cmd, cwd=root, check=True)

    if args.validate_pcs_bench and shutil.which("pcs-bench"):
        validate_cmd = [
            "pcs-bench",
            "validate-cases",
            "--suite",
            "labtrust-qc-release",
            "--pcs-core",
            str(pcs_core),
        ]
        print(" ".join(validate_cmd), flush=True)
        subprocess.run(validate_cmd, cwd=out.parent.parent, check=True)
    elif args.validate_pcs_bench:
        print("pcs-bench not on PATH; skipped validate-cases", flush=True)

    print(f"sync OK: {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
