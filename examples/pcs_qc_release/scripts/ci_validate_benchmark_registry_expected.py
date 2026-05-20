#!/usr/bin/env python3
"""CI: LabTrust pcs-bench registry expectations (and optional pcs-core sync check)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.benchmark_pcs_bench import (
    PCS_BENCH_SUITE_ID,
    expected_pcs_bench_case_ids,
)

EXPECTED = (
    ROOT
    / "examples"
    / "pcs_qc_release"
    / "policy"
    / "benchmark_registry.labtrust-qc-release.expected.json"
)


def _load_expected() -> dict:
    return json.loads(EXPECTED.read_text(encoding="utf-8"))


def _validate_labtrust_expected() -> None:
    exp_valid, exp_invalid = expected_pcs_bench_case_ids()
    doc = _load_expected()
    if doc["suite_id"] != PCS_BENCH_SUITE_ID:
        raise ValueError(f"suite_id mismatch: {doc['suite_id']}")
    if sorted(doc["valid_cases"]) != sorted(exp_valid):
        raise ValueError("expected.json valid_cases out of sync with generator")
    if sorted(doc["invalid_cases"]) != sorted(exp_invalid):
        raise ValueError("expected.json invalid_cases out of sync with generator")


def _validate_pcs_core_registry(registry_path: Path) -> None:
    doc = _load_expected()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entry = registry["suites"][PCS_BENCH_SUITE_ID]
    if entry.get("fixture_root") != doc["fixture_root"]:
        raise ValueError(
            f"fixture_root: registry {entry.get('fixture_root')!r} "
            f"!= expected {doc['fixture_root']!r}"
        )
    if sorted(entry.get("valid_cases", [])) != sorted(doc["valid_cases"]):
        raise ValueError("pcs-core registry valid_cases not synced to LabTrust ids")
    if sorted(entry.get("invalid_cases", [])) != sorted(doc["invalid_cases"]):
        raise ValueError("pcs-core registry invalid_cases not synced to LabTrust ids")
    workflow_ids = entry.get("workflow_ids") or []
    if doc["workflow_ids"][0] not in workflow_ids:
        raise ValueError("pcs-core registry workflow_ids missing labtrust profile id")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Optional pcs-core examples/benchmark_registry.valid.json",
    )
    args = parser.parse_args()
    _validate_labtrust_expected()
    print("OK benchmark registry expected slice")
    if args.registry is not None and args.registry.is_file():
        _validate_pcs_core_registry(args.registry.resolve())
        print(f"OK pcs-core registry synced: {args.registry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
