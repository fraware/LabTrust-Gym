#!/usr/bin/env python3
"""Materialize offline pcs-bench producer fixtures (ingest + on-disk sidecars)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.benchmark_pcs_bench_ingest import (
    PCS_BENCH_INGEST_NAME,
    refresh_ingest_artifact_ref_digests,
)
from labtrust_gym.pcs.benchmark_reproducibility import benchmark_reproducibility
from labtrust_gym.pcs.hash import pcs_digest
from labtrust_gym.pcs.workflow_profile import CANONICAL_QC_RELEASE_WORKFLOW_ID

FIXTURE_COMMIT = "0000000000000000000000000000000000000001"
FIXTURE_REPO = "https://github.com/fraware/LabTrust-Gym"
FIXTURE_TREE = ROOT / "tests" / "fixtures" / "pcs_bench_reproducibility"
LEGACY_INGEST = ROOT / "tests" / "fixtures" / "pcs_bench_ingest" / "labtrust" / PCS_BENCH_INGEST_NAME
FIXTURE_REL_OUT = FIXTURE_TREE.relative_to(ROOT).as_posix()


def _prune_fixture_tree(tree: Path) -> None:
    """Drop run scratch dirs not referenced by ingest artifact_refs."""
    for name in ("runs", "hash_stability_runs", "regeneration_reports"):
        path = tree / name
        if path.is_dir():
            shutil.rmtree(path)
    extra = tree / "benchmark_artifact_refs.labtrust.v0.json"
    if extra.is_file():
        extra.unlink()


def _fixture_commands() -> list[dict]:
    return [
        {
            "command": (
                "labtrust benchmark-reproducibility --workflow "
                f"{CANONICAL_QC_RELEASE_WORKFLOW_ID} --mode hash_stability "
                f"--runs 1 --out {FIXTURE_REL_OUT}"
            ),
            "exit_code": 0,
        }
    ]


def _pin_provenance(doc: dict) -> None:
    doc["source_repo"] = FIXTURE_REPO
    doc["source_commit"] = FIXTURE_COMMIT
    unsigned = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    doc["signature_or_digest"] = pcs_digest(unsigned)


def _rewrite_json(path: Path) -> None:
    if not path.is_file():
        return
    doc = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(doc, dict):
        _pin_provenance(doc)
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    import labtrust_gym.pcs.benchmark_case as bc

    release = ROOT / "examples" / "pcs_qc_release" / "release"
    if FIXTURE_TREE.exists():
        shutil.rmtree(FIXTURE_TREE)

    orig = bc._benchmark_provenance
    bc._benchmark_provenance = lambda _root=None: (FIXTURE_REPO, FIXTURE_COMMIT)  # type: ignore[assignment]
    try:
        benchmark_reproducibility(
            FIXTURE_TREE,
            workflow_key=CANONICAL_QC_RELEASE_WORKFLOW_ID,
            policy_root=ROOT,
            release_dir=release,
            pcs_core=None,
            runs=1,
            seed=42,
            mode="hash_stability",
            include_hash_stability=False,
            release_grade=False,
        )
    finally:
        bc._benchmark_provenance = orig  # type: ignore[assignment]

    _prune_fixture_tree(FIXTURE_TREE)

    ingest_path = FIXTURE_TREE / PCS_BENCH_INGEST_NAME
    ingest = json.loads(ingest_path.read_text(encoding="utf-8"))
    ingest["commands"] = _fixture_commands()
    _pin_provenance(ingest)
    for run in ingest.get("benchmark_runs") or []:
        if isinstance(run, dict):
            run["source_repo"] = FIXTURE_REPO
            run["source_commit"] = FIXTURE_COMMIT
            unsigned = {k: v for k, v in run.items() if k != "signature_or_digest"}
            run["signature_or_digest"] = pcs_digest(unsigned)
    for cov in ingest.get("coverage_reports") or []:
        if isinstance(cov, dict):
            cov["source_repo"] = FIXTURE_REPO
            cov["source_commit"] = FIXTURE_COMMIT
            unsigned = {k: v for k, v in cov.items() if k != "signature_or_digest"}
            cov["signature_or_digest"] = pcs_digest(unsigned)
    manifest_path = FIXTURE_TREE / "benchmark_manifest.v0.json"
    if manifest_path.is_file():
        _rewrite_json(manifest_path)
    runs_root = FIXTURE_TREE / "artifact_refs" / "benchmark_runs"
    if runs_root.is_dir():
        for run in ingest.get("benchmark_runs") or []:
            if isinstance(run, dict) and run.get("run_id"):
                sidecar = runs_root / f"{run['run_id']}.v0.json"
                sidecar.write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    cov_root = FIXTURE_TREE / "artifact_refs" / "coverage_reports"
    if cov_root.is_dir():
        for cov in ingest.get("coverage_reports") or []:
            if isinstance(cov, dict) and cov.get("coverage_id"):
                sidecar = cov_root / f"{cov['coverage_id']}.v0.json"
                sidecar.write_text(json.dumps(cov, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    refresh_ingest_artifact_ref_digests(
        FIXTURE_TREE,
        ingest,
        source_repo=FIXTURE_REPO,
        source_commit=FIXTURE_COMMIT,
    )
    pre_canonical = str(ingest["signature_or_digest"])
    from labtrust_gym.pcs.benchmark_pcs_bench_ingest import build_canonical_ingest_artifact_ref

    ingest["artifact_refs"] = [
        r for r in (ingest.get("artifact_refs") or []) if r.get("role") != "canonical_ingest"
    ]
    ingest["artifact_refs"].append(
        build_canonical_ingest_artifact_ref(
            ingest={"signature_or_digest": pre_canonical},
            source_repo=FIXTURE_REPO,
            source_commit=FIXTURE_COMMIT,
        )
    )
    _pin_provenance(ingest)
    ingest_path.write_text(json.dumps(ingest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    LEGACY_INGEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ingest_path, LEGACY_INGEST)

    from labtrust_gym.pcs.bench_schemas import validate_pcs_core_reproducibility_outputs

    pcs_core = ROOT.parent / "pcs-core"
    if (pcs_core / "schemas").is_dir():
        checks = validate_pcs_core_reproducibility_outputs(
            FIXTURE_TREE,
            pcs_core_root=pcs_core,
            policy_root=ROOT,
        )
        for label in checks:
            print(f"  OK {label}")

    print(f"wrote fixture tree {FIXTURE_TREE}")
    print(f"  legacy ingest {LEGACY_INGEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
