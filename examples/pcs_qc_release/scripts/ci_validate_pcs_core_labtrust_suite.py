#!/usr/bin/env python3
"""CI: validate pcs-core checkout labtrust-qc-release suite (LabTrust-generated layout)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.benchmark_cases import verify_benchmark_cases
from labtrust_gym.pcs.benchmark_pcs_bench import BENCHMARK_MANIFEST_NAME, is_pcs_bench_layout

EXPECTED = (
    ROOT
    / "examples"
    / "pcs_qc_release"
    / "policy"
    / "benchmark_registry.labtrust-qc-release.expected.json"
)
SUITE_REL = Path("benchmarks") / "labtrust-qc-release"


def _resolve_pcs_core() -> Path | None:
    for candidate in (ROOT / "pcs-core", ROOT.parent / "pcs-core"):
        if (candidate / "schemas" / "BenchmarkCase.v0.schema.json").is_file():
            return candidate.resolve()
    return None


def main() -> int:
    pcs_core = _resolve_pcs_core()
    if pcs_core is None:
        print("skip pcs-core labtrust suite validation (no checkout)")
        return 0

    suite = pcs_core / SUITE_REL
    if not is_pcs_bench_layout(suite):
        raise FileNotFoundError(
            f"pcs-core missing LabTrust pcs-bench suite at {suite}; "
            "run examples/pcs_qc_release/scripts/export_pcs_bench_to_pcs_core.ps1"
        )

    checks = verify_benchmark_cases(suite, policy_root=ROOT, pcs_core_root=pcs_core)
    for label in checks:
        print(f"OK {label}")

    manifest = json.loads((suite / BENCHMARK_MANIFEST_NAME).read_text(encoding="utf-8"))
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    exp_ids = sorted(expected["valid_cases"] + expected["invalid_cases"])
    if manifest.get("case_count") != len(exp_ids):
        raise ValueError(
            f"manifest case_count {manifest.get('case_count')} != {len(exp_ids)}"
        )
    if sorted(manifest.get("case_ids", [])) != exp_ids:
        raise ValueError("manifest case_ids do not match LabTrust expected registry slice")

    task_path = suite / "benchmark_task.v0.json"
    if task_path.is_file():
        from labtrust_gym.pcs.bench_schemas import validate_benchmark_task_pcs_core

        validate_benchmark_task_pcs_core(
            json.loads(task_path.read_text(encoding="utf-8")),
            pcs_core_root=pcs_core,
        )
        print("OK benchmark_task.v0 (pcs-core schema)")

    print(f"pcs-core labtrust suite CI OK ({suite})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
