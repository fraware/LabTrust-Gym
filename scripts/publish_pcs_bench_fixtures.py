#!/usr/bin/env python3
"""Publish LabTrust pcs-bench fixtures into sibling pcs-bench (offline producer gate)."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pcs-bench",
        type=Path,
        default=root.parent / "pcs-bench",
    )
    parser.add_argument(
        "--fixture-tree",
        type=Path,
        default=root / "tests" / "fixtures" / "pcs_bench_reproducibility",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Run generate_pcs_bench_ingest_fixture.py before publish",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        default=True,
    )
    args = parser.parse_args(argv)

    pcs_bench = args.pcs_bench.resolve()
    if not pcs_bench.is_dir():
        print(f"pcs-bench not found: {pcs_bench}", file=sys.stderr)
        return 1

    if args.regenerate:
        subprocess.run(
            [sys.executable, str(root / "scripts" / "generate_pcs_bench_ingest_fixture.py")],
            cwd=root,
            check=True,
        )

    fixture_tree = args.fixture_tree.resolve()
    if not (fixture_tree / "pcs_bench_ingest.v0.json").is_file():
        print(f"missing fixture tree: {fixture_tree}", file=sys.stderr)
        return 1

    for name in ("runs", "hash_stability_runs", "regeneration_reports"):
        path = fixture_tree / name
        if path.is_dir():
            shutil.rmtree(path)

    dest_ingest = (
        pcs_bench / "tests" / "fixtures" / "producer_ingest" / "labtrust_reproducibility"
    )
    dest_runs = pcs_bench / "runs" / "labtrust_reproducibility"
    _copy_tree(fixture_tree, dest_ingest)
    _copy_tree(fixture_tree, dest_runs)

    bench_dest = pcs_bench / "benchmarks" / "labtrust_qc_release"
    if not (bench_dest / "suite.yaml").is_file():
        sync = [sys.executable, str(root / "scripts" / "sync_pcs_bench_labtrust_suite.py")]
        print(" ".join(sync), flush=True)
        subprocess.run(sync, cwd=root, check=True)

    if args.validate and shutil.which("pcs-bench"):
        pcs_core = root.parent / "pcs-core"
        for target in (dest_ingest / "pcs_bench_ingest.v0.json",):
            cmd = [
                "pcs-bench",
                "validate-ingest",
                "--input",
                str(target),
                "--pcs-core",
                str(pcs_core),
            ]
            print(" ".join(cmd), flush=True)
            subprocess.run(cmd, check=True)

    print(f"published fixtures to {dest_ingest} and {dest_runs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
