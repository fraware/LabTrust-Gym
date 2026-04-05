#!/usr/bin/env python3
"""
Benchmark results pipeline: sweep folder to HTML + JSON presentation bundle.

Typical flow::

    python scripts/benchmark_suite.py publish --run-dir runs/gcp_full_benchmark

Writes ``index.html``, ``snapshot.json``, ``analysis_summary.json``,
``methods_matrix.csv``, and ``manifest.json``. Default output is a sibling
folder named ``<run_name>_report`` unless ``--out-dir`` is set.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_publish(run_dir: Path, scale_id: str, out_dir: Path | None) -> int:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "build_benchmark_report.py"),
        "--run-dir",
        str(run_dir),
        "--scale-id",
        scale_id,
    ]
    if out_dir is not None:
        cmd.extend(["--out-dir", str(out_dir)])
    proc = subprocess.run(cmd, cwd=str(ROOT))
    return int(proc.returncode)


def _cmd_open(report_dir: Path) -> int:
    index = (report_dir / "index.html").resolve()
    if not index.is_file():
        print(f"error: missing {index}", file=sys.stderr)
        return 1
    webbrowser.open(index.as_uri())
    return 0


def _cmd_paths(run_dir: Path) -> int:
    from labtrust_gym.benchmarks.presentation.pipeline import (
        default_report_out_dir,
    )

    print(default_report_out_dir(run_dir.resolve()))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "LabTrust Gym: benchmark sweep to HTML report and analysis JSON."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pub = sub.add_parser(
        "publish",
        help="Generate HTML report, snapshot, analysis, CSV matrix, manifest",
    )
    pub.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Sweep output (contains method_status.jsonl, cell folders)",
    )
    pub.add_argument(
        "--scale-id",
        type=str,
        default="medium_stress_signed_bus",
    )
    pub.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Report folder (default: sibling {run_name}_report)",
    )

    opn = sub.add_parser(
        "open",
        help="Open index.html from a report directory in the default browser",
    )
    opn.add_argument(
        "--report-dir",
        type=Path,
        required=True,
    )

    paths = sub.add_parser(
        "paths",
        help="Print the default report path for a run directory",
    )
    paths.add_argument("--run-dir", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "publish":
        return _run_publish(
            args.run_dir.resolve(),
            args.scale_id,
            args.out_dir,
        )
    if args.command == "open":
        return _cmd_open(args.report_dir.resolve())
    if args.command == "paths":
        return _cmd_paths(args.run_dir)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
