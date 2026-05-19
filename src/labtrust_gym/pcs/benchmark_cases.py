"""Generate BenchmarkCase.v0 suites from the QC release reference workflow."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.benchmark_case import (
    BENCHMARK_CASE_NAME,
    BENCHMARK_TASK_ID,
    EXPECTED_FAILURE_NAME,
    INPUT_ARTIFACTS_DIR,
    VALID_RELEASE_DIR_NAME,
    build_benchmark_case_document,
    build_valid_release_benchmark_case,
    localization_for,
    write_benchmark_case,
    write_expected_failure,
    write_expected_repair_hint,
)
from labtrust_gym.pcs.bench_schemas import validate_coverage_report
from labtrust_gym.pcs.failure_gallery import FailureCaseSpec, failure_case_specs
from labtrust_gym.pcs.release_protocol_producer import LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS
from labtrust_gym.pcs.workflow_profile import WorkflowProfileView, workflow_profile_view
from labtrust_gym.pcs.workflows.registry import get_workflow_by_key

BENCHMARK_INDEX_NAME = "benchmark_index.json"
_VALID_ARTIFACTS = tuple(
    dict.fromkeys(
        LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS
        + (
            "manifest.json",
            "trace_hash_alignment.json",
            "verification_result.json",
            "signed_science_claim_bundle.json",
            "regeneration_report.json",
            "proof_obligation_hints.json",
            "proof_obligation_identifiers.json",
            "formalization_readiness_report.json",
        )
    )
)

PCS_BENCH_LAYOUT_V0: dict[str, str] = {
    "version": "v0",
    "case_descriptor": BENCHMARK_CASE_NAME,
    "input_dir": INPUT_ARTIFACTS_DIR,
    "expected_failure": EXPECTED_FAILURE_NAME,
    "expected_repair_hint": "expected_repair_hint.json",
    "suite_index": BENCHMARK_INDEX_NAME,
    "coverage_report": "coverage_report.v0.json",
}


def _input_artifacts_dir(case_dir: Path) -> Path:
    d = case_dir / INPUT_ARTIFACTS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _copy_release_baseline(release_dir: Path, artifacts: Path) -> list[str]:
    written: list[str] = []
    for name in _VALID_ARTIFACTS:
        src = release_dir / name
        if src.is_file():
            shutil.copy2(src, artifacts / name)
            written.append(name)
    return written


def _write_case_readme(case_dir: Path, *, title: str, body: str, benchmark_doc: dict[str, Any]) -> None:
    readme = (
        f"# {title}\n\n"
        f"{body}\n\n"
        f"- Benchmark case: `{benchmark_doc['case_id']}`\n"
        f"- Detection layer: `{benchmark_doc['expected_detection_layer']}`\n"
        f"- Case kind: `{benchmark_doc['case_kind']}`\n"
    )
    (case_dir / "README.md").write_text(readme, encoding="utf-8")


def _build_valid_release_case(
    release_dir: Path,
    case_dir: Path,
    profile: WorkflowProfileView,
) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    artifacts = _input_artifacts_dir(case_dir)
    input_names = _copy_release_baseline(release_dir, artifacts)
    doc = build_valid_release_benchmark_case(
        workflow_property_id=profile.property_id,
        profile_workflow_id=profile.workflow_id,
    )
    write_benchmark_case(case_dir, doc)
    write_expected_repair_hint(
        case_dir,
        hint_kind="none",
        hint="Release package passes LabTrust verify-release-protocol and status policy.",
        repair_command=doc["expected_repair_command"],
    )
    (case_dir / "expected_failure.json").write_text(
        json.dumps(
            {
                "case_id": VALID_RELEASE_DIR_NAME,
                "expected_failing_check": None,
                "expected_failure_code": None,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_case_readme(
        case_dir,
        title=VALID_RELEASE_DIR_NAME,
        body="Positive control: committed release fixtures that pass protocol verification.",
        benchmark_doc=doc,
    )
    return {
        "case_id": VALID_RELEASE_DIR_NAME,
        "benchmark_case_id": doc["case_id"],
        "directory": VALID_RELEASE_DIR_NAME,
        "input_artifacts": input_names,
        "case_kind": doc["case_kind"],
    }


def _build_failure_benchmark_case(
    spec: FailureCaseSpec,
    *,
    policy_root: Path,
    release_dir: Path,
    case_dir: Path,
    profile: WorkflowProfileView,
) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    artifacts = _input_artifacts_dir(case_dir)
    input_names = spec.builder(policy_root, release_dir, artifacts, profile)
    loc = localization_for(spec.case_id)
    doc = build_benchmark_case_document(
        gallery_case_id=spec.case_id,
        workflow_property_id=profile.property_id,
        profile_workflow_id=profile.workflow_id,
        expected_failing_check=spec.expected_failing_check,
        expected_protocol_failure_code=spec.expected_failure_code,
        responsible_component=spec.responsible_component,
        repair_hint=spec.repair_hint,
    )
    write_benchmark_case(case_dir, doc)
    write_expected_failure(
        case_dir,
        gallery_case_id=spec.case_id,
        failing_check=spec.expected_failing_check,
        code=spec.expected_failure_code,
    )
    write_expected_repair_hint(
        case_dir,
        hint_kind=loc.repair_hint_kind,
        hint=spec.repair_hint,
        repair_command=loc.repair_command,
    )
    _write_case_readme(
        case_dir,
        title=spec.case_id,
        body=spec.description,
        benchmark_doc=doc,
    )
    return {
        "case_id": spec.case_id,
        "benchmark_case_id": doc["case_id"],
        "directory": spec.case_id,
        "input_artifacts": input_names,
        "case_kind": doc["case_kind"],
        "expected_detection_layer": doc["expected_detection_layer"],
    }


def build_coverage_report(
    *,
    workflow_property_id: str,
    case_entries: list[dict[str, Any]],
    benchmark_docs: list[dict[str, Any]],
) -> dict[str, Any]:
    kinds = sorted({d["case_kind"] for d in benchmark_docs})
    layers = sorted({d["expected_detection_layer"] for d in benchmark_docs})
    hints = sorted({d["expected_repair_hint_kind"] for d in benchmark_docs})
    report = {
        "schema_version": "v0",
        "workflow_id": workflow_property_id,
        "task_id": BENCHMARK_TASK_ID,
        "cases_covered": len(case_entries),
        "case_kinds_covered": kinds,
        "detection_layers_covered": layers,
        "repair_hint_kinds_covered": hints,
        "benchmark_cases": sorted(d["case_id"] for d in benchmark_docs),
    }
    validate_coverage_report(report)
    return report


def generate_benchmark_cases(
    out_dir: Path,
    *,
    workflow_key: str,
    policy_root: Path,
    release_dir: Path | None = None,
    profile_path: Path | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Generate BenchmarkCase.v0 directories under ``out_dir``.

    Deterministic for a fixed ``seed`` (stable case ordering and metadata).
    """
    profile = workflow_profile_view(profile_path, policy_root=policy_root)
    get_workflow_by_key(workflow_key, policy_root=policy_root, profile_path=profile.path)
    release = release_dir or (policy_root / "examples" / "pcs_qc_release" / "release")
    if not (release / "trace.json").is_file():
        raise FileNotFoundError(f"release baseline not found: {release}")

    out_dir = out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    specs = failure_case_specs(profile)
    case_entries: list[dict[str, Any]] = []
    benchmark_docs: list[dict[str, Any]] = []

    valid_entry = _build_valid_release_case(release, out_dir / VALID_RELEASE_DIR_NAME, profile)
    case_entries.append(valid_entry)
    benchmark_docs.append(
        json.loads((out_dir / VALID_RELEASE_DIR_NAME / BENCHMARK_CASE_NAME).read_text(encoding="utf-8"))
    )

    for spec in specs:
        entry = _build_failure_benchmark_case(
            spec,
            policy_root=policy_root,
            release_dir=release,
            case_dir=out_dir / spec.case_id,
            profile=profile,
        )
        case_entries.append(entry)
        benchmark_docs.append(
            json.loads((out_dir / spec.case_id / BENCHMARK_CASE_NAME).read_text(encoding="utf-8"))
        )

    try:
        profile_rel = str(profile.path.resolve().relative_to(policy_root.resolve())).replace("\\", "/")
    except ValueError:
        profile_rel = str(profile.path)

    coverage = build_coverage_report(
        workflow_property_id=profile.property_id,
        case_entries=case_entries,
        benchmark_docs=benchmark_docs,
    )
    (out_dir / "coverage_report.v0.json").write_text(
        json.dumps(coverage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    index = {
        "schema_version": "v0",
        "status": "passed",
        "workflow_id": profile.property_id,
        "profile_workflow_id": profile.workflow_id,
        "task_id": BENCHMARK_TASK_ID,
        "workflow_profile": profile_rel,
        "seed": seed,
        "pcs_bench": PCS_BENCH_LAYOUT_V0,
        "cases": case_entries,
        "out_dir": "benchmark",
    }
    (out_dir / BENCHMARK_INDEX_NAME).write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return index


def verify_benchmark_cases(benchmark_root: Path, *, policy_root: Path | None = None) -> list[str]:
    """Validate benchmark tree layout and BenchmarkCase.v0 documents."""
    from labtrust_gym.pcs.bench_schemas import validate_benchmark_case

    benchmark_root = benchmark_root.resolve()
    index_path = benchmark_root / BENCHMARK_INDEX_NAME
    if not index_path.is_file():
        raise FileNotFoundError(f"missing benchmark index: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    checks: list[str] = []
    for entry in index.get("cases", []):
        case_id = entry["case_id"]
        case_dir = benchmark_root / case_id
        if not case_dir.is_dir():
            raise FileNotFoundError(f"missing benchmark case directory: {case_dir}")
        doc = json.loads((case_dir / BENCHMARK_CASE_NAME).read_text(encoding="utf-8"))
        validate_benchmark_case(doc)
        for name in (
            "README.md",
            BENCHMARK_CASE_NAME,
            EXPECTED_FAILURE_NAME,
            "expected_repair_hint.json",
            INPUT_ARTIFACTS_DIR,
        ):
            if name == INPUT_ARTIFACTS_DIR:
                if not (case_dir / name).is_dir():
                    raise FileNotFoundError(f"{case_id} missing {name}/")
            elif not (case_dir / name).is_file():
                raise FileNotFoundError(f"{case_id} missing {name}")
        checks.append(f"benchmark_case.{case_id}")
    coverage_path = benchmark_root / "coverage_report.v0.json"
    if coverage_path.is_file():
        validate_coverage_report(json.loads(coverage_path.read_text(encoding="utf-8")))
        checks.append("coverage_report")
    profile_path = index.get("workflow_profile")
    if profile_path and policy_root is not None:
        from labtrust_gym.pcs.workflow_profile import assert_workflow_profile_valid, load_workflow_profile

        p = Path(profile_path)
        if not p.is_file():
            p = policy_root / profile_path
        assert_workflow_profile_valid(load_workflow_profile(p))
        checks.append("workflow_profile_valid")
    return checks
