"""Generate BenchmarkCase.v0 suites from the QC release reference workflow."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.benchmark_case import (
    BENCHMARK_CASE_NAME,
    BENCHMARK_TASK_ID,
    EXPECTED_FAILURE_NAME,
    INPUT_ARTIFACTS_DIR,
    LABTRUST_EXTENSION_NAME,
    VALID_RELEASE_DIR_NAME,
    build_benchmark_case_document,
    build_labtrust_extension,
    localization_for,
    valid_release_localization,
    write_benchmark_case,
    write_expected_failure,
    write_expected_repair_hint,
    write_labtrust_extension,
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
    "case_extension": LABTRUST_EXTENSION_NAME,
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


def _write_case_readme(
    case_dir: Path,
    *,
    title: str,
    body: str,
    benchmark_doc: dict[str, Any],
    detection_layer: str | None = None,
) -> None:
    layer_line = (
        f"- Detection layer: `{detection_layer}`\n" if detection_layer else ""
    )
    readme = (
        f"# {title}\n\n"
        f"{body}\n\n"
        f"- Benchmark case: `{benchmark_doc['case_id']}`\n"
        f"{layer_line}"
        f"- Case kind: `{benchmark_doc['case_kind']}`\n"
    )
    (case_dir / "README.md").write_text(readme, encoding="utf-8")


def _build_valid_release_case(
    release_dir: Path,
    case_dir: Path,
    profile: WorkflowProfileView,
    *,
    policy_root: Path,
) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    artifacts = _input_artifacts_dir(case_dir)
    input_names = _copy_release_baseline(release_dir, artifacts)
    doc = build_benchmark_case_document(
        gallery_case_id=VALID_RELEASE_DIR_NAME,
        workflow_property_id=profile.property_id,
        profile_workflow_id=profile.workflow_id,
        expected_failing_check=None,
        expected_protocol_failure_code=None,
        artifact_names=input_names,
        policy_root=policy_root,
    )
    write_benchmark_case(case_dir, doc)
    valid_loc = valid_release_localization()
    write_labtrust_extension(
        case_dir,
        build_labtrust_extension(
            gallery_case_id=VALID_RELEASE_DIR_NAME,
            profile_workflow_id=profile.workflow_id,
            expected_failing_check=None,
            expected_protocol_failure_code=None,
            loc=valid_loc,
        ),
    )
    write_expected_repair_hint(
        case_dir,
        failure_code="",
        responsible_component=doc["expected_responsible_component"],
        detection_layer="LabTrust",
        hint_kind="none",
        command=(
            "labtrust verify-release-protocol --release-dir examples/pcs_qc_release/release "
            "--pcs-core ../pcs-core"
        ),
        hint="Release package passes LabTrust verify-release-protocol and status policy.",
    )
    _write_case_readme(
        case_dir,
        title=VALID_RELEASE_DIR_NAME,
        body="Positive control: committed release fixtures that pass protocol verification.",
        benchmark_doc=doc,
        detection_layer="LabTrust",
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
        artifact_names=input_names,
        policy_root=policy_root,
    )
    write_benchmark_case(case_dir, doc)
    write_labtrust_extension(
        case_dir,
        build_labtrust_extension(
            gallery_case_id=spec.case_id,
            profile_workflow_id=profile.workflow_id,
            expected_failing_check=spec.expected_failing_check,
            expected_protocol_failure_code=spec.expected_failure_code,
            loc=loc,
        ),
    )
    write_expected_failure(
        case_dir,
        gallery_case_id=spec.case_id,
        failing_check=spec.expected_failing_check,
        benchmark_code=loc.benchmark_failure_code,
        protocol_code=spec.expected_failure_code,
    )
    write_expected_repair_hint(
        case_dir,
        failure_code=loc.benchmark_failure_code,
        responsible_component=doc["expected_responsible_component"],
        detection_layer=loc.detection_layer,
        hint_kind=loc.repair_hint_kind_for_fixture,
        command=loc.repair_command,
        hint=spec.repair_hint,
    )
    _write_case_readme(
        case_dir,
        title=spec.case_id,
        body=spec.description,
        benchmark_doc=doc,
        detection_layer=loc.detection_layer,
    )
    return {
        "case_id": spec.case_id,
        "benchmark_case_id": doc["case_id"],
        "directory": spec.case_id,
        "input_artifacts": input_names,
        "case_kind": doc["case_kind"],
    }


def _detection_layers_from_benchmark_root(benchmark_root: Path, index: dict[str, Any]) -> list[str]:
    del index
    layers: set[str] = set()
    for ext_path in benchmark_root.rglob(LABTRUST_EXTENSION_NAME):
        ext = json.loads(ext_path.read_text(encoding="utf-8"))
        layer = ext.get("expected_detection_layer")
        if layer:
            layers.add(layer)
    return sorted(layers)


def build_coverage_report(
    *,
    workflow_property_id: str,
    case_entries: list[dict[str, Any]],
    benchmark_docs: list[dict[str, Any]],
    benchmark_root: Path | None = None,
    index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kinds = sorted({d["case_kind"] for d in benchmark_docs})
    layers: list[str] = []
    if benchmark_root is not None and index is not None:
        layers = _detection_layers_from_benchmark_root(benchmark_root, index)
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
    pcs_bench_layout: bool = False,
) -> dict[str, Any]:
    """
    Generate BenchmarkCase.v0 directories under ``out_dir``.

    Deterministic for a fixed ``seed`` (stable case ordering and metadata).
    When ``pcs_bench_layout`` is true, emit ``valid/``, ``invalid/``, ``suite.yaml``,
    and ``benchmark_manifest.v0.json`` (pcs-bench canonical layout).
    """
    os.environ.setdefault("PCS_DETERMINISTIC", "1")
    if pcs_bench_layout:
        from labtrust_gym.pcs.benchmark_pcs_bench import generate_benchmark_cases_pcs_bench

        return generate_benchmark_cases_pcs_bench(
            out_dir,
            workflow_key=workflow_key,
            policy_root=policy_root,
            release_dir=release_dir,
            profile_path=profile_path,
            seed=seed,
        )

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

    print(f"benchmark: {VALID_RELEASE_DIR_NAME}", flush=True)
    valid_entry = _build_valid_release_case(
        release, out_dir / VALID_RELEASE_DIR_NAME, profile, policy_root=policy_root
    )
    case_entries.append(valid_entry)
    benchmark_docs.append(
        json.loads((out_dir / VALID_RELEASE_DIR_NAME / BENCHMARK_CASE_NAME).read_text(encoding="utf-8"))
    )

    for spec in specs:
        print(f"benchmark: {spec.case_id}", flush=True)
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
        benchmark_root=out_dir,
        index={
            "cases": case_entries,
        },
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


def _verify_single_case(
    case_id: str,
    case_dir: Path,
    doc: dict[str, Any],
    *,
    root: Path,
    pcs_core_root: Path | None,
    checks: list[str],
) -> None:
    from labtrust_gym.pcs.bench_schemas import (
        validate_benchmark_case,
        validate_benchmark_case_pcs_core,
        validate_expected_repair_hint,
        validate_labtrust_benchmark_extension,
    )
    from labtrust_gym.pcs.benchmark_case import PCS_BENCH_RELEASE_DIRECTORY

    validate_benchmark_case(doc, policy_root=root)
    rel_dir = str(doc["input_artifacts"].get("release_directory", ""))
    if not (rel_dir == PCS_BENCH_RELEASE_DIRECTORY or rel_dir.endswith("/input_artifacts")):
        raise ValueError(
            f"{case_id}: release_directory must be {PCS_BENCH_RELEASE_DIRECTORY!r} "
            "or end with /input_artifacts for pcs-bench layout"
        )
    if pcs_core_root is not None:
        validate_benchmark_case_pcs_core(doc, pcs_core_root=pcs_core_root)
    ext_path = case_dir / LABTRUST_EXTENSION_NAME
    if ext_path.is_file():
        validate_labtrust_benchmark_extension(
            json.loads(ext_path.read_text(encoding="utf-8")), policy_root=root
        )
    repair_path = case_dir / "expected_repair_hint.json"
    if repair_path.is_file():
        repair = json.loads(repair_path.read_text(encoding="utf-8"))
        validate_expected_repair_hint(repair, policy_root=root)
        if repair.get("responsible_component") != doc.get("expected_responsible_component"):
            raise ValueError(
                f"{case_id}: repair hint responsible_component does not match benchmark_case"
            )
    if doc.get("expected_status") == "passed" and (case_dir / EXPECTED_FAILURE_NAME).is_file():
        raise ValueError(f"{case_id}: valid case must not ship {EXPECTED_FAILURE_NAME}")
    required = [BENCHMARK_CASE_NAME, INPUT_ARTIFACTS_DIR]
    if doc.get("expected_status") != "passed":
        required.extend(
            [LABTRUST_EXTENSION_NAME, EXPECTED_FAILURE_NAME, "expected_repair_hint.json"]
        )
    else:
        if ext_path.is_file():
            required.append(LABTRUST_EXTENSION_NAME)
        if repair_path.is_file():
            required.append("expected_repair_hint.json")
    for name in required:
        if name == INPUT_ARTIFACTS_DIR:
            if not (case_dir / name).is_dir():
                raise FileNotFoundError(f"{case_id} missing {name}/")
        elif not (case_dir / name).is_file():
            raise FileNotFoundError(f"{case_id} missing {name}")
    checks.append(f"benchmark_case.{case_id}")
    if ext_path.is_file():
        checks.append(f"benchmark_extension.{case_id}")
    if repair_path.is_file():
        checks.append(f"repair_hint.{case_id}")


def verify_benchmark_cases(
    benchmark_root: Path,
    *,
    policy_root: Path | None = None,
    pcs_core_root: Path | None = None,
) -> list[str]:
    """Validate benchmark tree layout and BenchmarkCase.v0 documents."""
    from labtrust_gym.pcs.bench_schemas import (
        validate_benchmark_case,
        validate_benchmark_case_pcs_core,
        validate_expected_repair_hint,
        validate_labtrust_benchmark_extension,
    )

    from labtrust_gym.config import get_repo_root

    from labtrust_gym.pcs.benchmark_pcs_bench import (
        BENCHMARK_MANIFEST_NAME,
        is_pcs_bench_layout,
        iter_pcs_bench_cases,
    )

    benchmark_root = benchmark_root.resolve()
    root = policy_root or get_repo_root()
    checks: list[str] = []

    if is_pcs_bench_layout(benchmark_root):
        manifest_path = benchmark_root / BENCHMARK_MANIFEST_NAME
        if manifest_path.is_file():
            from labtrust_gym.pcs.bench_schemas import validate_benchmark_manifest

            validate_benchmark_manifest(
                json.loads(manifest_path.read_text(encoding="utf-8")), policy_root=root
            )
            checks.append("benchmark_manifest")
        case_iter = iter_pcs_bench_cases(benchmark_root)
        for case_path, doc in case_iter:
            case_id = doc["case_id"]
            case_dir = case_path.parent
            _verify_single_case(
                case_id,
                case_dir,
                doc,
                root=root,
                pcs_core_root=pcs_core_root,
                checks=checks,
            )
        coverage_path = benchmark_root / "coverage_report.v0.json"
        if coverage_path.is_file():
            validate_coverage_report(json.loads(coverage_path.read_text(encoding="utf-8")))
            checks.append("coverage_report")
        return checks

    index_path = benchmark_root / BENCHMARK_INDEX_NAME
    if not index_path.is_file():
        raise FileNotFoundError(f"missing benchmark index: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for entry in index.get("cases", []):
        case_id = entry["case_id"]
        case_dir = benchmark_root / case_id
        if not case_dir.is_dir():
            raise FileNotFoundError(f"missing benchmark case directory: {case_dir}")
        doc = json.loads((case_dir / BENCHMARK_CASE_NAME).read_text(encoding="utf-8"))
        _verify_single_case(
            case_id,
            case_dir,
            doc,
            root=root,
            pcs_core_root=pcs_core_root,
            checks=checks,
        )
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
