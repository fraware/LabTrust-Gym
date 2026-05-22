#!/usr/bin/env python3
"""CI: validate reproducibility ingest shape (temp run; golden optional)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.bench_schemas import (
    resolve_pcs_core_schema_root,
    validate_pcs_core_reproducibility_outputs,
)
from labtrust_gym.pcs.benchmark_reproducibility import benchmark_reproducibility
from labtrust_gym.pcs.workflow_profile import CANONICAL_QC_RELEASE_WORKFLOW_ID

GOLDEN = ROOT / "examples" / "pcs_qc_release" / "benchmark_ingest" / "golden"


def main() -> int:
    pcs_core = resolve_pcs_core_schema_root(ROOT.parent / "pcs-core")
    if pcs_core is None:
        print("skip benchmark ingest validation (no pcs-core)")
        return 0

    release = ROOT / "examples" / "pcs_qc_release" / "release"
    with tempfile.TemporaryDirectory(prefix="labtrust_ingest_") as tmp:
        out = Path(tmp)
        benchmark_reproducibility(
            out,
            workflow_key="hospital_lab.qc_release",
            policy_root=ROOT,
            release_dir=release,
            pcs_core=pcs_core,
            runs=2,
            seed=42,
            mode="hash_stability",
            include_hash_stability=False,
            validate_pcs_core_output=pcs_core,
        )
        checks = validate_pcs_core_reproducibility_outputs(
            out, pcs_core_root=pcs_core, policy_root=ROOT
        )
        import json

        from labtrust_gym.pcs.benchmark_pcs_bench_ingest import PCS_BENCH_INGEST_NAME

        ingest = json.loads((out / PCS_BENCH_INGEST_NAME).read_text(encoding="utf-8"))
        if ingest["workflow_id"] != CANONICAL_QC_RELEASE_WORKFLOW_ID:
            raise SystemExit(
                f"ingest workflow_id must be {CANONICAL_QC_RELEASE_WORKFLOW_ID!r}"
            )
        n_runs = len(ingest.get("benchmark_runs") or [])
        n_cov = len(ingest.get("coverage_reports") or [])
        if len(ingest.get("artifact_refs") or []) < n_runs + n_cov:
            raise SystemExit("ingest must include pcs-core artifact_refs per embedded run/coverage")
        manifest = json.loads((out / "benchmark_manifest.v0.json").read_text(encoding="utf-8"))
        if manifest.get("evidence_grade") != "developer":
            raise SystemExit("hash_stability CI run must use developer evidence_grade")
        for label in checks:
            print(f"  OK {label}")

    if GOLDEN.is_dir() and (GOLDEN / "pcs_bench_ingest.v0.json").is_file():
        checks = validate_pcs_core_reproducibility_outputs(
            GOLDEN, pcs_core_root=pcs_core, policy_root=ROOT
        )
        print(f"committed golden OK ({len(checks)} checks)")
    else:
        print("no committed golden/ (run materialize_benchmark_ingest_golden.py to add)")

    print("benchmark ingest CI OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
