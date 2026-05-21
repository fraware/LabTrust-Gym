#!/usr/bin/env python3
"""Materialize examples/pcs_qc_release/benchmark_packet/ for pcs-bench smoke runs."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.benchmark_cases import generate_benchmark_cases, verify_benchmark_cases

PACKET = ROOT / "examples" / "pcs_qc_release" / "benchmark_packet"
RELEASE = ROOT / "examples" / "pcs_qc_release" / "release"


def main() -> int:
    tmp = PACKET / "_build"
    try:
        if tmp.exists():
            shutil.rmtree(tmp)
        generate_benchmark_cases(
            tmp,
            workflow_key="hospital_lab.qc_release",
            policy_root=ROOT,
            release_dir=RELEASE,
            seed=42,
        )
        verify_benchmark_cases(tmp, policy_root=ROOT)

        mappings = (
            ("valid_release", "valid_release"),
            ("trace_hash_tamper", "invalid_trace_hash_tamper"),
        )
        for src_name, dst_name in mappings:
            src = tmp / src_name
            dst = PACKET / dst_name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

        valid_doc = json.loads(
            (PACKET / "valid_release" / "benchmark_case.v0.json").read_text(encoding="utf-8")
        )
        invalid_doc = json.loads(
            (PACKET / "invalid_trace_hash_tamper" / "benchmark_case.v0.json").read_text(
                encoding="utf-8"
            )
        )
        expected = {
            "schema_version": "v0",
            "benchmark_suite_id": "labtrust-qc-release-v0",
            "cases": [
                {
                    "case_id": valid_doc["case_id"],
                    "gallery_case_id": "valid_release",
                    "expected_status": "passed",
                },
                {
                    "case_id": invalid_doc["case_id"],
                    "gallery_case_id": "invalid_trace_hash_tamper",
                    "expected_status": "failed",
                    "expected_failure_code": invalid_doc.get("expected_failure_code"),
                },
            ],
        }
        (PACKET / "expected_report.json").write_text(
            json.dumps(expected, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    print("benchmark_packet OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
