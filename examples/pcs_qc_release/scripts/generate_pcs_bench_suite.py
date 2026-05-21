#!/usr/bin/env python3
"""Generate pcs-bench canonical suite into pcs-core (or custom --out)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.bench_schemas import resolve_pcs_core_schema_root
from labtrust_gym.pcs.benchmark_pcs_bench import (
    PCS_BENCH_SUITE_ID,
    cleanup_pcs_bench_orphans,
    generate_benchmark_cases_pcs_bench,
)


def _default_out() -> Path:
    for candidate in (
        ROOT.parent / "pcs-core" / "benchmarks" / "labtrust-qc-release",
        ROOT.parent / "pcs-bench" / "benchmarks" / "labtrust_qc_release",
    ):
        if candidate.parent.is_dir():
            return candidate
    return ROOT.parent / "pcs-core" / "benchmarks" / "labtrust-qc-release"


def _default_registry() -> Path | None:
    path = ROOT.parent / "pcs-core" / "examples" / "benchmark_registry.valid.json"
    return path if path.is_file() else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Suite root (default: ../pcs-core/benchmarks/labtrust-qc-release)",
    )
    parser.add_argument(
        "--fixture-root",
        default="benchmarks/labtrust-qc-release",
        help="Fixture root path stored in pcs-core registry (default: benchmarks/labtrust-qc-release)",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="pcs-core examples/benchmark_registry.valid.json to sync case ids",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip schema verification (faster smoke)",
    )
    parser.add_argument(
        "--validate-pcs-core-output",
        type=Path,
        default=None,
        help="pcs-core root for strict schema validation (default: ../pcs-core when present)",
    )
    args = parser.parse_args()
    out = (args.out or _default_out()).resolve()
    release = ROOT / "examples" / "pcs_qc_release" / "release"
    registry = args.registry if args.registry is not None else _default_registry()
    cleanup_pcs_bench_orphans(out)
    print(f"Generating pcs-bench suite at {out} (seed={args.seed})...", flush=True)

    pcs_core_validate = args.validate_pcs_core_output
    if pcs_core_validate is None and not args.skip_verify:
        pcs_core_validate = ROOT.parent / "pcs-core"
    schema_root = resolve_pcs_core_schema_root(pcs_core_validate)

    result = generate_benchmark_cases_pcs_bench(
        out,
        workflow_key="hospital_lab.qc_release",
        policy_root=ROOT,
        release_dir=release,
        seed=args.seed,
        suite_id=PCS_BENCH_SUITE_ID,
        suite_fixture_root=args.fixture_root,
        pcs_core_registry=registry,
        validate_pcs_core_output=schema_root,
    )
    checks: list[str] = []
    if not args.skip_verify and schema_root is not None:
        from labtrust_gym.pcs.bench_schemas import validate_pcs_core_benchmark_suite_outputs

        checks = validate_pcs_core_benchmark_suite_outputs(
            out, pcs_core_root=schema_root, policy_root=ROOT
        )

    if len(result["valid_cases"]) != 1 or len(result["invalid_cases"]) != 12:
        raise RuntimeError(
            f"unexpected case count: {len(result['valid_cases'])} valid, "
            f"{len(result['invalid_cases'])} invalid"
        )

    print(f"OK wrote pcs-bench suite to {out}")
    print(f"  valid: {len(result['valid_cases'])} invalid: {len(result['invalid_cases'])}")
    if registry is not None and registry.is_file():
        print(f"  registry synced: {registry}")
    for label in checks[:5]:
        print(f"  {label}")
    if len(checks) > 5:
        print(f"  ... ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
