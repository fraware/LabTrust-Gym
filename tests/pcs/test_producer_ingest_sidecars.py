"""Producer ingest sidecar digest alignment and release-grade path coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.bench_schemas import (
    validate_producer_ingest_contract,
    validate_producer_ingest_sidecars,
    validate_release_grade_ingest_contract,
)
from labtrust_gym.pcs.benchmark_pcs_bench_ingest import (
    EVIDENCE_GRADE_RELEASE,
    RELEASE_GRADE_INGEST_REF_PATHS,
)
from labtrust_gym.pcs.benchmark_reproducibility import (
    PCS_BENCH_INGEST_NAME,
    _portable_command_out,
    benchmark_reproducibility,
)
from labtrust_gym.pcs.workflow_profile import CANONICAL_QC_RELEASE_WORKFLOW_ID


def test_release_grade_required_ref_paths_defined() -> None:
    assert PCS_BENCH_INGEST_NAME in RELEASE_GRADE_INGEST_REF_PATHS
    assert "benchmark_run.v0.json" in RELEASE_GRADE_INGEST_REF_PATHS


def test_hash_stability_ingest_sidecars_validate(
    repo_root: Path, release_dir: Path, tmp_path: Path
) -> None:
    out = tmp_path / "repro"
    benchmark_reproducibility(
        out,
        workflow_key="hospital_lab.qc_release",
        policy_root=repo_root,
        release_dir=release_dir,
        runs=1,
        seed=1,
        mode="hash_stability",
        include_hash_stability=False,
        release_grade=False,
    )
    ingest_path = out / PCS_BENCH_INGEST_NAME
    ingest = json.loads(ingest_path.read_text(encoding="utf-8"))
    checks = validate_producer_ingest_sidecars(out, ingest, ingest_path=ingest_path)
    assert "pcs_bench_ingest.sidecars" in checks
    contract = validate_producer_ingest_contract(
        ingest,
        ingest_path=ingest_path,
        policy_root=repo_root,
        out_dir=out,
    )
    assert "pcs_bench_ingest.sidecars" in contract


def test_ingest_commands_use_repo_relative_out(repo_root: Path) -> None:
    out = repo_root / "tests" / "fixtures" / "pcs_bench_reproducibility"
    rel = _portable_command_out(out, repo_root)
    assert rel == "tests/fixtures/pcs_bench_reproducibility"
    ingest = json.loads(
        (repo_root / "tests/fixtures/pcs_bench_reproducibility/pcs_bench_ingest.v0.json").read_text(
            encoding="utf-8"
        )
    )
    cmd = str((ingest.get("commands") or [{}])[0].get("command", ""))
    assert "C:" not in cmd
    assert "tests/fixtures/pcs_bench_reproducibility" in cmd


def test_release_grade_contract_on_live_output(repo_root: Path) -> None:
    live = repo_root / "benchmark_runs" / "labtrust_reproducibility"
    ingest_path = live / PCS_BENCH_INGEST_NAME
    manifest_path = live / "benchmark_manifest.v0.json"
    if not ingest_path.is_file() or not manifest_path.is_file():
        pytest.skip("run make pcs-bench-producer to create live output")
    ingest = json.loads(ingest_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("evidence_grade") != EVIDENCE_GRADE_RELEASE:
        pytest.skip("live output is not release-grade")
    checks = validate_release_grade_ingest_contract(ingest, manifest, ingest_path=ingest_path)
    assert "pcs_bench_ingest.release_grade" in checks
    assert ingest["workflow_id"] == CANONICAL_QC_RELEASE_WORKFLOW_ID
    full = validate_producer_ingest_contract(
        ingest,
        ingest_path=ingest_path,
        policy_root=repo_root,
        out_dir=live,
        release_grade=True,
        manifest_doc=manifest,
    )
    assert "pcs_bench_ingest.release_grade" in full
