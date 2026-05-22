#!/usr/bin/env python3
"""Write tests/fixtures/pcs_bench_ingest/labtrust/pcs_bench_ingest.v0.json (offline gate)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.benchmark_pcs_bench_ingest import (
    PRODUCER_ID,
    REPRODUCIBILITY_SUITE_ID,
    build_pcs_bench_ingest,
    build_pcs_core_benchmark_runs_from_reproducibility,
    build_pcs_core_reproducibility_artifact_refs,
    build_release_reproducibility_coverage_report,
    build_reproducibility_benchmark_manifest,
)
from labtrust_gym.pcs.benchmark_report import build_reproducibility_pcs_benchmark_report
from labtrust_gym.pcs.workflow_profile import CANONICAL_QC_RELEASE_WORKFLOW_ID

FIXTURE_COMMIT = "0000000000000000000000000000000000000001"
FIXTURE_REPO = "https://github.com/fraware/LabTrust-Gym"
OUT = ROOT / "tests" / "fixtures" / "pcs_bench_ingest" / "labtrust" / "pcs_bench_ingest.v0.json"


def _fixture_provenance() -> tuple[str, str]:
    return FIXTURE_REPO, FIXTURE_COMMIT


def main() -> int:
    import labtrust_gym.pcs.benchmark_case as bc

    orig = bc._benchmark_provenance
    bc._benchmark_provenance = _fixture_provenance  # type: ignore[assignment]
    try:
        run_doc = {
            "schema_version": "v0",
            "benchmark_id": "labtrust-reproducibility-v0",
            "workflow_id": CANONICAL_QC_RELEASE_WORKFLOW_ID,
            "mode": "hash_stability",
            "seed": 42,
            "runs": 1,
            "per_run": [],
            "aggregate": {
                "command_deterministic": True,
                "certifyedge_success_rate": 1.0,
                "pcs_core_validation_stable": True,
            },
            "signature_or_digest": "sha256:" + "a" * 64,
        }
        coverage = {
            "schema_version": "v0",
            "workflow_id": CANONICAL_QC_RELEASE_WORKFLOW_ID,
            "task_id": "labtrust-qc-release-reproducibility-v0",
            "reproducibility_passed": True,
            "runs": 1,
            "mode": "hash_stability",
        }
        pcs_cov = build_release_reproducibility_coverage_report(
            run_doc=run_doc,
            reproducibility_coverage=coverage,
            policy_root=ROOT,
        )
        per_run = [
            {
                "run_index": 0,
                "duration_ms": 100,
                "artifact_hashes": {"trace.json": "sha256:" + "b" * 64},
                "certificate_id": "cert-fixture",
                "certifyedge_call_success": True,
                "release_protocol_validation_passed": True,
                "status_policy_validation_passed": True,
                "pcs_core_validation_passed": True,
            }
        ]
        pcs_runs = build_pcs_core_benchmark_runs_from_reproducibility(
            per_run=per_run,
            mode="hash_stability",
            policy_root=ROOT,
        )
        with tempfile.TemporaryDirectory(prefix="labtrust_fixture_") as tmp:
            tmp_path = Path(tmp)
            refs = build_pcs_core_reproducibility_artifact_refs(
                out_dir=tmp_path,
                pcs_runs=pcs_runs,
                pcs_coverage=pcs_cov,
                source_repo=FIXTURE_REPO,
                source_commit=FIXTURE_COMMIT,
                write_sidecars=True,
            )
            ingest = build_pcs_bench_ingest(
                workflow_id=CANONICAL_QC_RELEASE_WORKFLOW_ID,
                benchmark_runs=pcs_runs,
                coverage_reports=[pcs_cov],
                policy_root=ROOT,
                suite_id=REPRODUCIBILITY_SUITE_ID,
                artifact_refs=refs,
                logs=["fixture: offline producer gate"],
            )
    finally:
        bc._benchmark_provenance = orig  # type: ignore[assignment]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(ingest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert ingest["producer_id"] == PRODUCER_ID
    assert ingest["workflow_id"] == CANONICAL_QC_RELEASE_WORKFLOW_ID
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
