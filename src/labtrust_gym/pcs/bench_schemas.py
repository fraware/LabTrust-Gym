"""JSON Schema validation for pcs-bench machine-readable artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.errors import PolicyLoadError
from labtrust_gym.policy.loader import load_json, validate_against_schema

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[misc, assignment]

FAILURE_CASE_MANIFEST_SCHEMA = (
    "policy/schemas/pcs/FailureCaseManifest.v0.schema.json"
)
REGENERATION_REPORT_SCHEMA = "policy/schemas/pcs/RegenerationReport.v0.schema.json"
PROOF_OBLIGATION_HINTS_SCHEMA = "policy/schemas/pcs/ProofObligationHints.v0.schema.json"
PROOF_OBLIGATION_IDENTIFIERS_SCHEMA = (
    "policy/schemas/pcs/ProofObligationIdentifiers.v0.schema.json"
)
FORMALIZATION_READINESS_REPORT_SCHEMA = (
    "policy/schemas/pcs/FormalizationReadinessReport.v0.schema.json"
)
WORKFLOW_PROFILE_FORMALIZATION_SCHEMA = (
    "policy/schemas/pcs/WorkflowProfile.formalization.extension.schema.json"
)
BENCHMARK_CASE_SCHEMA = "policy/schemas/pcs/BenchmarkCase.v0.schema.json"
BENCHMARK_RUN_SCHEMA = "policy/schemas/pcs/BenchmarkRun.v0.schema.json"
COVERAGE_REPORT_SCHEMA = "policy/schemas/pcs/CoverageReport.v0.schema.json"
REPRODUCIBILITY_COVERAGE_REPORT_SCHEMA = (
    "policy/schemas/pcs/ReproducibilityCoverageReport.v0.schema.json"
)
REPRODUCIBILITY_BENCHMARK_REPORT_SCHEMA = (
    "policy/schemas/pcs/ReproducibilityBenchmarkReport.v0.schema.json"
)
LABTRUST_BENCHMARK_EXTENSION_SCHEMA = (
    "policy/schemas/pcs/LabtrustBenchmarkExtension.v0.schema.json"
)
EXPECTED_REPAIR_HINT_SCHEMA = "policy/schemas/pcs/ExpectedRepairHint.v0.schema.json"
BENCHMARK_MANIFEST_SCHEMA = "policy/schemas/pcs/BenchmarkManifest.v0.schema.json"
REPRODUCIBILITY_BENCHMARK_MANIFEST_SCHEMA = (
    "policy/schemas/pcs/ReproducibilityBenchmarkManifest.v0.schema.json"
)
HASH_STABILITY_REPORT_SCHEMA = "policy/schemas/pcs/HashStabilityReport.v0.schema.json"
PCS_BENCH_INGEST_SCHEMA = "policy/schemas/pcs/PcsBenchIngest.v0.schema.json"
BENCHMARK_ARTIFACT_REF_SCHEMA = "policy/schemas/pcs/BenchmarkArtifactRef.v0.schema.json"


def resolve_pcs_core_schema_root(pcs_core: Path | None) -> Path | None:
    """Return pcs-core repo root when ``pcs_core`` is a release dir or repo root."""
    if pcs_core is None:
        return None
    pcs_core = pcs_core.resolve()
    if (pcs_core / "schemas" / "BenchmarkCase.v0.schema.json").is_file():
        return pcs_core
    parent = pcs_core.parent
    if (parent / "schemas" / "BenchmarkCase.v0.schema.json").is_file():
        return parent
    return None


def _schema_path(rel: str, *, policy_root: Path | None = None) -> Path:
    root = policy_root or get_repo_root()
    path = root / rel
    if not path.is_file():
        raise FileNotFoundError(f"PCS bench schema not found: {path}")
    return path


def validate_failure_case_manifest(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    """Raise ``PolicyLoadError`` when ``doc`` is not FailureCaseManifest.v0."""
    schema_path = _schema_path(FAILURE_CASE_MANIFEST_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_regeneration_report_doc(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    """Raise ``PolicyLoadError`` when ``doc`` is not RegenerationReport.v0."""
    schema_path = _schema_path(REGENERATION_REPORT_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_proof_obligation_hints(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(PROOF_OBLIGATION_HINTS_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_proof_obligation_identifiers(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(PROOF_OBLIGATION_IDENTIFIERS_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_formalization_readiness_report(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(FORMALIZATION_READINESS_REPORT_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_workflow_profile_formalization(
    block: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(WORKFLOW_PROFILE_FORMALIZATION_SCHEMA, policy_root=policy_root)
    validate_against_schema(block, load_json(schema_path), path=schema_path)


def validate_benchmark_case(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(BENCHMARK_CASE_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_benchmark_run(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(BENCHMARK_RUN_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_coverage_report(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(COVERAGE_REPORT_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_reproducibility_coverage_report(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(REPRODUCIBILITY_COVERAGE_REPORT_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_reproducibility_benchmark_report(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(REPRODUCIBILITY_BENCHMARK_REPORT_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_labtrust_benchmark_extension(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(LABTRUST_BENCHMARK_EXTENSION_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_expected_repair_hint(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(EXPECTED_REPAIR_HINT_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def _pcs_core_schema_registry(schemas_dir: Path):
    import json

    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    registry: Registry = Registry()
    for path in sorted(schemas_dir.glob("*.json")):
        registry = registry.with_resource(
            path.name,
            Resource.from_contents(json.loads(path.read_text(encoding="utf-8"))),
        )
    return registry, Draft202012Validator


def validate_benchmark_manifest(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(BENCHMARK_MANIFEST_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_reproducibility_benchmark_manifest(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(REPRODUCIBILITY_BENCHMARK_MANIFEST_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def _validate_pcs_core_doc(
    doc: dict[str, Any],
    *,
    pcs_core_root: Path,
    schema_name: str,
    label: str,
) -> None:
    if jsonschema is None:
        raise PolicyLoadError(
            pcs_core_root,
            "jsonschema is required for pcs-core schema validation",
        )
    schemas_dir = pcs_core_root / "schemas"
    schema_path = schemas_dir / schema_name
    if not schema_path.is_file():
        raise FileNotFoundError(f"pcs-core {label} schema not found: {schema_path}")
    schema = load_json(schema_path)
    registry, validator_cls = _pcs_core_schema_registry(schemas_dir)
    try:
        validator_cls(schema, registry=registry).validate(doc)
    except jsonschema.ValidationError as e:
        raise PolicyLoadError(schema_path, f"pcs-core {label} validation failed: {e}") from e


def validate_benchmark_run_pcs_core(
    doc: dict[str, Any],
    *,
    pcs_core_root: Path,
) -> None:
    _validate_pcs_core_doc(
        doc, pcs_core_root=pcs_core_root, schema_name="BenchmarkRun.v0.schema.json", label="BenchmarkRun"
    )


def validate_coverage_report_pcs_core(
    doc: dict[str, Any],
    *,
    pcs_core_root: Path,
) -> None:
    _validate_pcs_core_doc(
        doc,
        pcs_core_root=pcs_core_root,
        schema_name="CoverageReport.v0.schema.json",
        label="CoverageReport",
    )


def validate_benchmark_report_pcs_core(
    doc: dict[str, Any],
    *,
    pcs_core_root: Path,
) -> None:
    _validate_pcs_core_doc(
        doc,
        pcs_core_root=pcs_core_root,
        schema_name="BenchmarkReport.v0.schema.json",
        label="BenchmarkReport",
    )


def validate_pcs_bench_ingest(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(PCS_BENCH_INGEST_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)
    for ref in doc.get("artifact_refs", []):
        validate_benchmark_artifact_ref(ref, policy_root=policy_root)


def validate_benchmark_artifact_ref(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(BENCHMARK_ARTIFACT_REF_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_benchmark_artifact_ref_pcs_core(
    doc: dict[str, Any],
    *,
    pcs_core_root: Path,
) -> None:
    _validate_pcs_core_doc(
        doc,
        pcs_core_root=pcs_core_root,
        schema_name="BenchmarkArtifactRef.v0.schema.json",
        label="BenchmarkArtifactRef",
    )


def validate_hash_stability_report(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    schema_path = _schema_path(HASH_STABILITY_REPORT_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_benchmark_task_pcs_core(
    doc: dict[str, Any],
    *,
    pcs_core_root: Path,
) -> None:
    """Validate against pcs-core ``BenchmarkTask.v0`` schema."""
    if jsonschema is None:
        raise PolicyLoadError(
            pcs_core_root,
            "jsonschema is required for pcs-core schema validation",
        )
    schemas_dir = pcs_core_root / "schemas"
    schema_path = schemas_dir / "BenchmarkTask.v0.schema.json"
    if not schema_path.is_file():
        raise FileNotFoundError(f"pcs-core BenchmarkTask schema not found: {schema_path}")
    schema = load_json(schema_path)
    registry, validator_cls = _pcs_core_schema_registry(schemas_dir)
    try:
        validator_cls(schema, registry=registry).validate(doc)
    except jsonschema.ValidationError as e:
        raise PolicyLoadError(schema_path, f"pcs-core BenchmarkTask validation failed: {e}") from e


def validate_producer_ingest_sidecars(
    out_dir: Path,
    ingest_doc: dict[str, Any],
    *,
    ingest_path: Path | str = "pcs_bench_ingest.v0.json",
) -> list[str]:
    """Verify on-disk sidecars exist and ``artifact_refs[].sha256`` matches file digests."""
    import json

    from labtrust_gym.pcs.hash import file_digest, pcs_digest

    checks: list[str] = []
    root = out_dir.resolve()
    for index, ref in enumerate(ingest_doc.get("artifact_refs") or []):
        if not isinstance(ref, dict):
            continue
        rel = ref.get("path")
        if not isinstance(rel, str) or not rel.strip():
            raise PolicyLoadError(ingest_path, f"artifact_refs[{index}]: missing path")
        sidecar = root / rel.replace("\\", "/")
        if not sidecar.is_file():
            raise PolicyLoadError(
                ingest_path,
                f"artifact_refs[{index}]: sidecar missing at {rel!r}",
            )
        expected = ref.get("sha256")
        if not isinstance(expected, str):
            raise PolicyLoadError(ingest_path, f"artifact_refs[{index}]: missing sha256")
        if ref.get("role") == "canonical_ingest":
            continue
        if sidecar.suffix.lower() == ".json":
            doc = json.loads(sidecar.read_text(encoding="utf-8"))
            if not isinstance(doc, dict):
                raise PolicyLoadError(ingest_path, f"artifact_refs[{index}]: JSON must be object")
            actual = str(doc.get("signature_or_digest") or pcs_digest(doc))
        else:
            actual = file_digest(sidecar)
        if actual != expected:
            raise PolicyLoadError(
                ingest_path,
                f"artifact_refs[{index}]: sha256 mismatch for {rel!r} "
                f"(expected {expected}, got {actual})",
            )
    checks.append("pcs_bench_ingest.sidecars")
    return checks


def validate_release_grade_ingest_contract(
    ingest_doc: dict[str, Any],
    manifest_doc: dict[str, Any],
    *,
    ingest_path: Path | str = "pcs_bench_ingest.v0.json",
    runs: int = 5,
) -> list[str]:
    """Release-grade manifest + ingest sidecar path coverage."""
    from labtrust_gym.pcs.benchmark_pcs_bench_ingest import (
        EVIDENCE_GRADE_RELEASE,
        RELEASE_GRADE_INGEST_REF_PATHS,
    )

    checks: list[str] = []
    if manifest_doc.get("evidence_grade") != EVIDENCE_GRADE_RELEASE:
        raise PolicyLoadError(
            ingest_path,
            f"manifest evidence_grade must be {EVIDENCE_GRADE_RELEASE!r}",
        )
    if manifest_doc.get("mode") != "full_regeneration":
        raise PolicyLoadError(ingest_path, "manifest mode must be full_regeneration")
    if int(manifest_doc.get("runs") or 0) < runs:
        raise PolicyLoadError(ingest_path, f"manifest runs must be >={runs}")
    if not manifest_doc.get("certifyedge_live"):
        raise PolicyLoadError(ingest_path, "manifest certifyedge_live must be true")
    if not manifest_doc.get("pcs_core_validation"):
        raise PolicyLoadError(ingest_path, "manifest pcs_core_validation must be true")
    if not manifest_doc.get("canonical_hashes_stable"):
        raise PolicyLoadError(ingest_path, "manifest canonical_hashes_stable must be true")

    ref_paths = {
        str(r.get("path")).replace("\\", "/")
        for r in (ingest_doc.get("artifact_refs") or [])
        if isinstance(r, dict) and r.get("path")
    }
    missing = sorted(RELEASE_GRADE_INGEST_REF_PATHS - ref_paths)
    if missing:
        raise PolicyLoadError(
            ingest_path,
            f"release-grade ingest missing artifact_refs paths: {missing}",
        )
    commands = ingest_doc.get("commands") or []
    if not commands:
        raise PolicyLoadError(ingest_path, "release-grade ingest requires non-empty commands")
    commit = str(ingest_doc.get("source_commit", ""))
    if commit == "0" * 40:
        raise PolicyLoadError(ingest_path, "release-grade ingest source_commit must not be all zeros")
    checks.append("pcs_bench_ingest.release_grade")
    return checks


def validate_producer_ingest_contract(
    ingest_doc: dict[str, Any],
    *,
    ingest_path: Path | str = "pcs_bench_ingest.v0.json",
    policy_root: Path | None = None,
    pcs_core_root: Path | None = None,
    min_artifact_refs: int | None = None,
    out_dir: Path | None = None,
    release_grade: bool = False,
    manifest_doc: dict[str, Any] | None = None,
) -> list[str]:
    """
    LabTrust producer gate for ``PcsBenchIngest.v0`` (canonical workflow + artifact refs).

    Ingest embeds pcs-core runs/coverage and lists pcs-core + LabTrust sidecar ``artifact_refs``.
    When ``out_dir`` is set, sidecar files are checked for digest alignment.

    Returns check labels for CI logging.
    """
    from labtrust_gym.pcs.workflow_profile import CANONICAL_QC_RELEASE_WORKFLOW_ID

    checks: list[str] = []
    validate_pcs_bench_ingest(ingest_doc, policy_root=policy_root)
    checks.append("pcs_bench_ingest.labtrust")
    if pcs_core_root is not None:
        validate_pcs_bench_ingest_pcs_core(ingest_doc, pcs_core_root=pcs_core_root)
        checks.append("pcs_bench_ingest.pcs_core")
    if ingest_doc.get("workflow_id") != CANONICAL_QC_RELEASE_WORKFLOW_ID:
        raise PolicyLoadError(
            ingest_path,
            f"workflow_id must be {CANONICAL_QC_RELEASE_WORKFLOW_ID!r}, "
            f"got {ingest_doc.get('workflow_id')!r}",
        )
    checks.append("pcs_bench_ingest.workflow_id")
    if len(ingest_doc.get("benchmark_runs") or []) < 1:
        raise PolicyLoadError(ingest_path, "expected at least one benchmark_run")
    if len(ingest_doc.get("coverage_reports") or []) < 1:
        raise PolicyLoadError(ingest_path, "expected at least one coverage_report")
    runs = ingest_doc.get("benchmark_runs") or []
    coverage = ingest_doc.get("coverage_reports") or []
    expected_refs = len(runs) + len(coverage)
    min_refs = expected_refs if min_artifact_refs is None else min_artifact_refs
    refs = ingest_doc.get("artifact_refs") or []
    if len(refs) < min_refs:
        raise PolicyLoadError(
            ingest_path,
            f"expected >={min_refs} pcs-core artifact_refs, got {len(refs)}",
        )
    from labtrust_gym.pcs.benchmark_pcs_bench_ingest import (
        is_labtrust_extended_artifact_ref,
        is_pcs_core_compatible_artifact_ref,
    )

    for ref in refs:
        if not is_pcs_core_compatible_artifact_ref(ref) and not is_labtrust_extended_artifact_ref(
            ref
        ):
            raise PolicyLoadError(
                ingest_path,
                f"ingest artifact_refs must be pcs-core or LabTrust extended: "
                f"{ref.get('artifact_type')!r} role={ref.get('role')!r}",
            )
        validate_benchmark_artifact_ref(ref, policy_root=policy_root)
        if is_labtrust_extended_artifact_ref(ref):
            continue
        digest = ref.get("sha256")
        atype = ref.get("artifact_type")
        embedded = [
            row
            for row in (runs if atype == "BenchmarkRun.v0" else coverage)
            if isinstance(row, dict) and row.get("signature_or_digest") == digest
        ]
        if not embedded:
            raise PolicyLoadError(
                ingest_path,
                f"artifact_ref sha256 does not match embedded {atype}: {digest!r}",
            )
    checks.append("pcs_bench_ingest.artifact_refs")
    if out_dir is not None:
        checks.extend(validate_producer_ingest_sidecars(out_dir, ingest_doc, ingest_path=ingest_path))
    if release_grade:
        if manifest_doc is None:
            raise PolicyLoadError(ingest_path, "release_grade validation requires manifest_doc")
        checks.extend(
            validate_release_grade_ingest_contract(
                ingest_doc,
                manifest_doc,
                ingest_path=ingest_path,
            )
        )
    return checks


def validate_pcs_bench_ingest_pcs_core(
    doc: dict[str, Any],
    *,
    pcs_core_root: Path,
) -> None:
    """Validate against pcs-core ``PcsBenchIngest.v0`` schema."""
    if jsonschema is None:
        raise PolicyLoadError(
            pcs_core_root,
            "jsonschema is required for pcs-core schema validation",
        )
    schemas_dir = pcs_core_root / "schemas"
    schema_path = schemas_dir / "PcsBenchIngest.v0.schema.json"
    if not schema_path.is_file():
        raise FileNotFoundError(f"pcs-core PcsBenchIngest schema not found: {schema_path}")
    from labtrust_gym.pcs.benchmark_pcs_bench_ingest import is_pcs_core_compatible_artifact_ref

    schema = load_json(schema_path)
    registry, validator_cls = _pcs_core_schema_registry(schemas_dir)
    refs = list(doc.get("artifact_refs") or [])
    body = {k: v for k, v in doc.items() if k != "artifact_refs"}
    pcs_refs = [r for r in refs if is_pcs_core_compatible_artifact_ref(r)]
    if pcs_refs:
        body["artifact_refs"] = pcs_refs
    try:
        validator_cls(schema, registry=registry).validate(body)
    except jsonschema.ValidationError as e:
        raise PolicyLoadError(schema_path, f"pcs-core ingest validation failed: {e}") from e
    except Exception as e:
        raise PolicyLoadError(schema_path, f"pcs-core ingest validation failed: {e}") from e
    for ref in pcs_refs:
        validate_benchmark_artifact_ref_pcs_core(ref, pcs_core_root=pcs_core_root)
    for run in doc.get("benchmark_runs", []):
        validate_benchmark_run_pcs_core(run, pcs_core_root=pcs_core_root)
    for report in doc.get("coverage_reports", []):
        validate_coverage_report_pcs_core(report, pcs_core_root=pcs_core_root)


def validate_pcs_core_reproducibility_outputs(
    out_dir: Path,
    *,
    pcs_core_root: Path,
    policy_root: Path | None = None,
) -> list[str]:
    """
    Validate reproducibility benchmark artifacts against LabTrust and pcs-core schemas.

    Returns human-readable check labels (for CLI logging).
    """
    from labtrust_gym.pcs.benchmark_pcs_bench_ingest import PCS_BENCH_INGEST_NAME
    from labtrust_gym.pcs.benchmark_reproducibility import (
        BENCHMARK_RUN_NAME,
        COVERAGE_REPORT_NAME,
    )

    import json

    from labtrust_gym.pcs.workflow_profile import CANONICAL_QC_RELEASE_WORKFLOW_ID

    checks: list[str] = []
    out_dir = out_dir.resolve()
    pcs_core_root = pcs_core_root.resolve()

    run_path = out_dir / BENCHMARK_RUN_NAME
    run_doc = json.loads(run_path.read_text(encoding="utf-8"))
    validate_benchmark_run(run_doc, policy_root=policy_root)
    checks.append("benchmark_run.labtrust")

    coverage_path = out_dir / COVERAGE_REPORT_NAME
    coverage_doc = json.loads(coverage_path.read_text(encoding="utf-8"))
    validate_reproducibility_coverage_report(coverage_doc, policy_root=policy_root)
    checks.append("coverage_report.labtrust")

    ingest_path = out_dir / PCS_BENCH_INGEST_NAME
    ingest_doc = json.loads(ingest_path.read_text(encoding="utf-8"))
    manifest_path = out_dir / "benchmark_manifest.v0.json"
    manifest_doc: dict[str, Any] | None = None
    if manifest_path.is_file():
        manifest_doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    from labtrust_gym.pcs.benchmark_pcs_bench_ingest import EVIDENCE_GRADE_RELEASE

    release_grade = (
        isinstance(manifest_doc, dict)
        and manifest_doc.get("evidence_grade") == EVIDENCE_GRADE_RELEASE
    )
    checks.extend(
        validate_producer_ingest_contract(
            ingest_doc,
            ingest_path=ingest_path,
            policy_root=policy_root,
            pcs_core_root=pcs_core_root,
            out_dir=out_dir,
            release_grade=release_grade,
            manifest_doc=manifest_doc,
        )
    )

    if manifest_path.is_file() and manifest_doc is not None:
        validate_reproducibility_benchmark_manifest(manifest_doc, policy_root=policy_root)
        checks.append("benchmark_manifest.labtrust")
        if manifest_doc.get("workflow_id") != CANONICAL_QC_RELEASE_WORKFLOW_ID:
            raise PolicyLoadError(
                manifest_path,
                f"manifest workflow_id must be {CANONICAL_QC_RELEASE_WORKFLOW_ID!r}",
            )
        checks.append("benchmark_manifest.workflow_id")

    report_path = out_dir / "benchmark_report.v0.json"
    if report_path.is_file():
        report_doc = json.loads(report_path.read_text(encoding="utf-8"))
        validate_benchmark_report_pcs_core(report_doc, pcs_core_root=pcs_core_root)
        checks.append("benchmark_report.pcs_core")

    return checks


def validate_pcs_core_benchmark_suite_outputs(
    benchmark_root: Path,
    *,
    pcs_core_root: Path,
    policy_root: Path | None = None,
) -> list[str]:
    """Validate a pcs-bench case suite tree against pcs-core schemas."""
    from labtrust_gym.pcs.benchmark_cases import verify_benchmark_cases
    from labtrust_gym.pcs.benchmark_pcs_bench import BENCHMARK_TASK_NAME

    checks = verify_benchmark_cases(
        benchmark_root,
        policy_root=policy_root,
        pcs_core_root=pcs_core_root,
    )
    task_path = benchmark_root / BENCHMARK_TASK_NAME
    if task_path.is_file():
        import json

        task_doc = json.loads(task_path.read_text(encoding="utf-8"))
        validate_benchmark_task_pcs_core(task_doc, pcs_core_root=pcs_core_root)
        checks.append("benchmark_task.pcs_core")
    return checks


def validate_benchmark_case_pcs_core(
    doc: dict[str, Any],
    *,
    pcs_core_root: Path,
) -> None:
    """Validate against pcs-core's BenchmarkCase.v0 schema (requires checkout)."""
    if jsonschema is None:
        raise PolicyLoadError(
            pcs_core_root,
            "jsonschema is required for pcs-core schema validation",
        )
    schemas_dir = pcs_core_root / "schemas"
    schema_path = schemas_dir / "BenchmarkCase.v0.schema.json"
    if not schema_path.is_file():
        raise FileNotFoundError(f"pcs-core BenchmarkCase schema not found: {schema_path}")
    schema = load_json(schema_path)
    registry, validator_cls = _pcs_core_schema_registry(schemas_dir)
    try:
        validator_cls(schema, registry=registry).validate(doc)
    except jsonschema.ValidationError as e:
        raise PolicyLoadError(schema_path, f"pcs-core schema validation failed: {e}") from e
    except Exception as e:
        raise PolicyLoadError(schema_path, f"pcs-core schema validation failed: {e}") from e
