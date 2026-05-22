#!/usr/bin/env python3
"""Release-grade LabTrust reproducibility producer + optional pcs-bench ingest validation."""

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
    parser.add_argument("--pcs-bench", type=Path, default=root.parent / "pcs-bench")
    parser.add_argument(
        "--out",
        type=Path,
        default=root / "benchmark_runs" / "labtrust_reproducibility",
    )
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--certifyedge-bin", default="certifyedge")
    args = parser.parse_args(argv)

    pcs_core = args.pcs_core.resolve()
    out = args.out.resolve()
    ingest = out / "pcs_bench_ingest.v0.json"

    cmd = [
        "labtrust",
        "benchmark-reproducibility",
        "--workflow",
        "hospital_lab.qc_release",
        "--mode",
        "full_regeneration",
        "--pcs-core",
        str(pcs_core),
        "--certifyedge-bin",
        args.certifyedge_bin,
        "--runs",
        str(args.runs),
        "--out",
        str(out),
        "--validate-pcs-core-output",
        str(pcs_core),
        "--release-grade",
    ]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=root, check=True)

    from labtrust_gym.pcs.bench_schemas import validate_pcs_core_reproducibility_outputs

    pcs_errors = validate_pcs_core_reproducibility_outputs(
        out,
        pcs_core_root=pcs_core,
        policy_root=root,
    )
    for label in pcs_errors:
        print(f"  OK {label}", flush=True)

    if shutil.which("pcs-bench"):
        validate_cmd = [
            "pcs-bench",
            "validate-ingest",
            "--input",
            str(ingest),
            "--pcs-core",
            str(pcs_core),
            "--release-grade",
        ]
        print(" ".join(validate_cmd), flush=True)
        subprocess.run(validate_cmd, check=True)
    else:
        print(
            "pcs-bench not found; skipped validate-ingest "
            "(LabTrust --validate-pcs-core-output already ran)",
            flush=True,
        )

    print(f"pcs-bench-producer OK: {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
