"""pcs-bench directory layout: valid/invalid cases, suite.yaml, benchmark_manifest.v0.json."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from labtrust_gym.pcs.benchmark_case import (
    BENCHMARK_CASE_NAME,
    BENCHMARK_TASK_ID,
    EXPECTED_FAILURE_NAME,
    PCS_BENCH_RELEASE_DIRECTORY,
    benchmark_case_id_for,
)
from labtrust_gym.pcs.benchmark_cases import build_coverage_report, generate_benchmark_cases
from labtrust_gym.pcs.bench_schemas import validate_benchmark_manifest
from labtrust_gym.pcs.hash import pcs_digest
from labtrust_gym.version import __version__

SUITE_YAML_NAME = "suite.yaml"
BENCHMARK_MANIFEST_NAME = "benchmark_manifest.v0.json"
PCS_BENCH_SUITE_ID = "labtrust-qc-release-v0"
GENERATOR_NAME = "labtrust"
BENCHMARK_TASK_NAME = "benchmark_task.v0.json"
PROFILE_WORKFLOW_ID = "labtrust.qc_release_v0.1"
PCS_BENCH_EXPECTED_VALID_COUNT = 1
PCS_BENCH_EXPECTED_INVALID_COUNT = 12
VALID_GALLERY_CASE_ID = "valid_release"
FAILURE_GALLERY_CASE_IDS: tuple[str, ...] = (
    "missing_qc_result",
    "unauthorized_release",
    "trace_hash_tamper",
    "certificate_id_tamper",
    "stale_trace_after_certificate",
    "legacy_handoff_file",
    "placeholder_commit",
    "lean_trace_hash_mismatch",
    "lean_rejected_certificate",
    "lean_stale_certificate",
    "lean_signed_hash_mismatch",
    "scientific_memory_import_failure",
)


@dataclass
class PcsBenchCaseRef:
    case_id: str
    polarity: Literal["valid", "invalid"]
    path: str
    gallery_case_id: str
    benchmark_doc: dict[str, Any]


def _polarity_for_doc(doc: dict[str, Any]) -> Literal["valid", "invalid"]:
    return "valid" if doc.get("expected_status") == "passed" else "invalid"


def expected_pcs_bench_case_ids() -> tuple[list[str], list[str]]:
    """Canonical pcs-bench case ids LabTrust generates (replaces legacy pcs-core slugs)."""
    valid = [benchmark_case_id_for(VALID_GALLERY_CASE_ID)]
    invalid = [benchmark_case_id_for(g) for g in FAILURE_GALLERY_CASE_IDS]
    return valid, invalid


def assert_pcs_bench_case_counts(case_refs: list[PcsBenchCaseRef]) -> None:
    valid = [r for r in case_refs if r.polarity == "valid"]
    invalid = [r for r in case_refs if r.polarity == "invalid"]
    if len(valid) != PCS_BENCH_EXPECTED_VALID_COUNT:
        raise RuntimeError(
            f"expected {PCS_BENCH_EXPECTED_VALID_COUNT} valid case(s), got {len(valid)}"
        )
    if len(invalid) != PCS_BENCH_EXPECTED_INVALID_COUNT:
        raise RuntimeError(
            f"expected {PCS_BENCH_EXPECTED_INVALID_COUNT} invalid case(s), got {len(invalid)}"
        )
    exp_valid, exp_invalid = expected_pcs_bench_case_ids()
    if sorted(r.case_id for r in valid) != sorted(exp_valid):
        raise RuntimeError("valid case ids do not match LabTrust benchmark profile")
    if sorted(r.case_id for r in invalid) != sorted(exp_invalid):
        raise RuntimeError("invalid case ids do not match LabTrust benchmark profile")


def cleanup_pcs_bench_orphans(suite_root: Path) -> None:
    """Remove interrupted generator debris (``.staging``, legacy flat dirs)."""
    staging = suite_root / ".staging"
    if staging.is_dir():
        shutil.rmtree(staging, ignore_errors=True)
    for name in (VALID_GALLERY_CASE_ID, *FAILURE_GALLERY_CASE_IDS):
        legacy = suite_root / name
        if legacy.is_dir():
            shutil.rmtree(legacy, ignore_errors=True)


def build_suite_yaml(
    *,
    suite_id: str,
    workflow_id: str,
    task_id: str,
    case_refs: list[PcsBenchCaseRef],
    seed: int,
    generator_version: str,
) -> str:
    valid_cases = sorted(r.case_id for r in case_refs if r.polarity == "valid")
    invalid_cases = sorted(r.case_id for r in case_refs if r.polarity == "invalid")
    doc = {
        "schema_version": "v0",
        "suite_id": suite_id,
        "workflow_id": workflow_id,
        "task_id": task_id,
        "generator": GENERATOR_NAME,
        "generator_version": generator_version,
        "seed": seed,
        "valid_cases": valid_cases,
        "invalid_cases": invalid_cases,
        "cases": [
            {
                "case_id": r.case_id,
                "polarity": r.polarity,
                "path": r.path.replace("\\", "/"),
            }
            for r in sorted(case_refs, key=lambda x: (x.polarity, x.case_id))
        ],
    }
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)


def pcs_bench_release_directory(*, suite_fixture_root: str, case_ref: PcsBenchCaseRef) -> str:
    """Path from pcs-core repo root to case input artifacts (for ``resolve_release_directory``)."""
    root = suite_fixture_root.strip("/").replace("\\", "/")
    return f"{root}/{case_ref.path}/input_artifacts"


def patch_benchmark_case_release_paths(
    suite_root: Path,
    case_refs: list[PcsBenchCaseRef],
    *,
    suite_fixture_root: str,
) -> None:
    """Rewrite ``release_directory`` to pcs-core–absolute fixture paths."""
    for ref in case_refs:
        case_path = suite_root / ref.path / BENCHMARK_CASE_NAME
        doc = json.loads(case_path.read_text(encoding="utf-8"))
        doc["input_artifacts"]["release_directory"] = pcs_bench_release_directory(
            suite_fixture_root=suite_fixture_root, case_ref=ref
        )
        from labtrust_gym.pcs.benchmark_case import _finalize_signature

        doc["signature_or_digest"] = _finalize_signature(doc)
        case_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ref.benchmark_doc.update(doc)


def build_benchmark_task_v0(
    *,
    suite_id: str,
    task_id: str,
    workflow_id: str,
    case_refs: list[PcsBenchCaseRef],
    source_repo: str,
    source_commit: str,
    suite_fixture_root: str,
) -> dict[str, Any]:
    from labtrust_gym.pcs.benchmark_case import _finalize_signature

    doc: dict[str, Any] = {
        "schema_version": "v0",
        "task_id": task_id,
        "workflow_id": workflow_id,
        "domain": "process_safety",
        "description": f"PCS benchmark task for {suite_id} (LabTrust-generated)",
        "input_case_set": {
            "path": suite_fixture_root.strip("/").replace("\\", "/"),
            "case_count": len(case_refs),
        },
        "expected_outputs": {
            "report_artifact_type": "BenchmarkReport.v0",
            "minimum_pass_rate": 1.0,
        },
        "metrics": [
            "release_reproducibility",
            "failure_localization",
            "certificate_completeness",
            "registry_coverage",
            "formal_check_coverage",
            "scientific_memory_interpretability",
        ],
        "success_criteria": {
            "minimum_pass_rate": 1.0,
            "minimum_failure_localization_accuracy": 1.0,
            "minimum_formal_check_coverage": 1.0,
            "minimum_registry_coverage": 0.95,
        },
        "source_repo": source_repo,
        "source_commit": source_commit,
    }
    doc["signature_or_digest"] = _finalize_signature(doc)
    return doc


def sync_pcs_core_benchmark_registry(
    registry_path: Path,
    *,
    suite_id: str,
    valid_cases: list[str],
    invalid_cases: list[str],
    fixture_root: str,
    workflow_id: str = PROFILE_WORKFLOW_ID,
) -> dict[str, Any]:
    """Update pcs-core ``benchmark_registry`` suite entry from LabTrust-generated case ids."""
    registry_path = registry_path.resolve()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    suites = registry.get("suites")
    if not isinstance(suites, dict) or suite_id not in suites:
        raise KeyError(f"suite {suite_id!r} not in {registry_path}")
    entry = suites[suite_id]
    entry["fixture_root"] = fixture_root.replace("\\", "/")
    entry["valid_cases"] = sorted(valid_cases)
    entry["invalid_cases"] = sorted(invalid_cases)
    if workflow_id:
        entry["workflow_ids"] = [workflow_id]
    registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return entry


def build_benchmark_manifest(
    *,
    suite_id: str,
    workflow_id: str,
    source_repo: str,
    source_commit: str,
    case_refs: list[PcsBenchCaseRef],
    coverage_report_path: str,
    seed: int,
) -> dict[str, Any]:
    case_ids = [r.case_id for r in case_refs]
    doc: dict[str, Any] = {
        "schema_version": "v0",
        "suite_id": suite_id,
        "workflow_id": workflow_id,
        "task_id": BENCHMARK_TASK_ID,
        "generator": GENERATOR_NAME,
        "generator_version": __version__,
        "source_repo": source_repo,
        "source_commit": source_commit,
        "seed": seed,
        "case_count": len(case_ids),
        "case_ids": sorted(case_ids),
        "cases": [
            {
                "case_id": r.case_id,
                "polarity": r.polarity,
                "path": r.path.replace("\\", "/"),
                "gallery_case_id": r.gallery_case_id,
            }
            for r in case_refs
        ],
        "coverage_report": coverage_report_path.replace("\\", "/"),
    }
    unsigned = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    doc["signature_or_digest"] = pcs_digest(unsigned)
    validate_benchmark_manifest(doc)
    return doc


def _relocate_to_pcs_bench_layout(staging_dir: Path, out_dir: Path) -> list[PcsBenchCaseRef]:
    """Move flat LabTrust benchmark tree into valid/invalid/{case_id}/ layout."""
    refs: list[PcsBenchCaseRef] = []
    for case_dir in sorted(p for p in staging_dir.iterdir() if p.is_dir()):
        bench_path = case_dir / BENCHMARK_CASE_NAME
        if not bench_path.is_file():
            continue
        doc = json.loads(bench_path.read_text(encoding="utf-8"))
        polarity = _polarity_for_doc(doc)
        case_id = str(doc["case_id"])
        dest = out_dir / polarity / case_id
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(case_dir), str(dest))
        if polarity == "valid":
            failure_path = dest / EXPECTED_FAILURE_NAME
            if failure_path.is_file():
                failure_path.unlink()
        refs.append(
            PcsBenchCaseRef(
                case_id=case_id,
                polarity=polarity,
                path=f"{polarity}/{case_id}",
                gallery_case_id=case_dir.name,
                benchmark_doc=doc,
            )
        )
    return refs


def generate_benchmark_cases_pcs_bench(
    out_dir: Path,
    *,
    workflow_key: str,
    policy_root: Path,
    release_dir: Path | None = None,
    profile_path: Path | None = None,
    seed: int = 42,
    suite_id: str = PCS_BENCH_SUITE_ID,
    suite_fixture_root: str | None = None,
    pcs_core_registry: Path | None = None,
) -> dict[str, Any]:
    """
    Generate a pcs-bench fixture tree under ``out_dir``.

    Layout: ``suite.yaml``, ``benchmark_manifest.v0.json``, ``coverage_report.v0.json``,
    ``valid/<case_id>/``, ``invalid/<case_id>/``.
    """
    from labtrust_gym.pcs.benchmark_case import _benchmark_provenance

    out_dir = out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    cleanup_pcs_bench_orphans(out_dir)
    staging = out_dir / ".staging"
    try:
        index = generate_benchmark_cases(
            staging,
            workflow_key=workflow_key,
            policy_root=policy_root,
            release_dir=release_dir,
            profile_path=profile_path,
            seed=seed,
        )
        case_refs = _relocate_to_pcs_bench_layout(staging, out_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    assert_pcs_bench_case_counts(case_refs)

    fixture_root = (suite_fixture_root or out_dir.name).replace("\\", "/")
    patch_benchmark_case_release_paths(
        out_dir, case_refs, suite_fixture_root=fixture_root
    )

    benchmark_docs = [ref.benchmark_doc for ref in case_refs]

    coverage = build_coverage_report(
        workflow_property_id=index["workflow_id"],
        case_entries=[
            {
                "case_id": r.gallery_case_id,
                "benchmark_case_id": r.case_id,
                "directory": r.path,
                "case_kind": r.benchmark_doc["case_kind"],
            }
            for r in case_refs
        ],
        benchmark_docs=benchmark_docs,
        benchmark_root=out_dir,
        index={"cases": [{"case_id": r.gallery_case_id} for r in case_refs]},
    )
    coverage_path = out_dir / "coverage_report.v0.json"
    coverage_path.write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    source_repo, source_commit = _benchmark_provenance(policy_root)
    manifest = build_benchmark_manifest(
        suite_id=suite_id,
        workflow_id=index["workflow_id"],
        source_repo=source_repo,
        source_commit=source_commit,
        case_refs=case_refs,
        coverage_report_path="coverage_report.v0.json",
        seed=seed,
    )
    (out_dir / BENCHMARK_MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / SUITE_YAML_NAME).write_text(
        build_suite_yaml(
            suite_id=suite_id,
            workflow_id=index["workflow_id"],
            task_id=BENCHMARK_TASK_ID,
            case_refs=case_refs,
            seed=seed,
            generator_version=__version__,
        ),
        encoding="utf-8",
    )
    task_doc = build_benchmark_task_v0(
        suite_id=suite_id,
        task_id=BENCHMARK_TASK_ID,
        workflow_id=PROFILE_WORKFLOW_ID,
        case_refs=case_refs,
        source_repo=source_repo,
        source_commit=source_commit,
        suite_fixture_root=fixture_root,
    )
    (out_dir / BENCHMARK_TASK_NAME).write_text(
        json.dumps(task_doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if pcs_core_registry is not None and pcs_core_registry.is_file():
        sync_pcs_core_benchmark_registry(
            pcs_core_registry,
            suite_id=suite_id,
            valid_cases=[r.case_id for r in case_refs if r.polarity == "valid"],
            invalid_cases=[r.case_id for r in case_refs if r.polarity == "invalid"],
            fixture_root=fixture_root,
        )
    return {
        "layout": "pcs-bench",
        "suite_id": suite_id,
        "out_dir": str(out_dir),
        "manifest": BENCHMARK_MANIFEST_NAME,
        "suite": SUITE_YAML_NAME,
        "cases": [ref.case_id for ref in case_refs],
        "valid_cases": [r.case_id for r in case_refs if r.polarity == "valid"],
        "invalid_cases": [r.case_id for r in case_refs if r.polarity == "invalid"],
    }


def is_pcs_bench_layout(benchmark_root: Path) -> bool:
    return (benchmark_root / SUITE_YAML_NAME).is_file() or (
        benchmark_root / BENCHMARK_MANIFEST_NAME
    ).is_file()


def iter_pcs_bench_cases(benchmark_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    discovered: list[tuple[Path, dict[str, Any]]] = []
    for polarity in ("valid", "invalid"):
        base = benchmark_root / polarity
        if not base.is_dir():
            continue
        for case_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            case_path = case_dir / BENCHMARK_CASE_NAME
            if case_path.is_file():
                discovered.append(
                    (case_path, json.loads(case_path.read_text(encoding="utf-8")))
                )
    return discovered
