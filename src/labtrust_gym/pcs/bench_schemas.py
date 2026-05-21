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
    schema = load_json(schema_path)
    registry, validator_cls = _pcs_core_schema_registry(schemas_dir)
    try:
        validator_cls(schema, registry=registry).validate(doc)
    except jsonschema.ValidationError as e:
        raise PolicyLoadError(schema_path, f"pcs-core ingest validation failed: {e}") from e
    except Exception as e:
        raise PolicyLoadError(schema_path, f"pcs-core ingest validation failed: {e}") from e
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
    validate_pcs_bench_ingest(ingest_doc, policy_root=policy_root)
    checks.append("pcs_bench_ingest.labtrust")
    validate_pcs_bench_ingest_pcs_core(ingest_doc, pcs_core_root=pcs_core_root)
    checks.append("pcs_bench_ingest.pcs_core")

    manifest_path = out_dir / "benchmark_manifest.v0.json"
    if manifest_path.is_file():
        manifest_doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate_reproducibility_benchmark_manifest(manifest_doc, policy_root=policy_root)
        checks.append("benchmark_manifest.labtrust")

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
