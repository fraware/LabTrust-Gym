"""Build PcsBenchIngest.v0 exports for pcs-bench (aligned with pcs-core benchmark_compat)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.benchmark_case import (
    _benchmark_provenance,
    _finalize_signature,
)
from labtrust_gym.pcs.benchmark_pcs_bench import PCS_BENCH_SUITE_ID
from labtrust_gym.pcs.hash import pcs_digest

PCS_BENCH_INGEST_NAME = "pcs_bench_ingest.v0.json"
LABTRUST_EXTENDED_ARTIFACT_REFS_NAME = "benchmark_artifact_refs.labtrust.v0.json"
PRODUCER_ID = "labtrust-gym"
REPRODUCIBILITY_SUITE_ID = "labtrust-qc-reproducibility-v0"
REPRODUCIBILITY_TASK_ID = "labtrust-qc-release-reproducibility-v0"
REPRODUCIBILITY_CASE_ID = "labtrust-valid-release-v0"
EVIDENCE_GRADE_RELEASE = "release"
EVIDENCE_GRADE_DEVELOPER = "developer"
_REPRO_BASE_TIME = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)

_PCS_CORE_ARTIFACT_REF_TYPES = frozenset(
    {
        "BenchmarkCase.v0",
        "BenchmarkRun.v0",
        "CoverageReport.v0",
        "FailureLocalizationResult.v0",
        "ExplainQualityReport.v0",
        "ProfileCoverageReport.v0",
        "MetricSummary.v0",
    }
)
_PCS_CORE_ARTIFACT_REF_ROLES = frozenset({"producer_export", "ingest_bundle", "primary"})
_LABTRUST_EXTENDED_ARTIFACT_REF_TYPES = frozenset(
    {
        "BenchmarkReport.v0",
        "LabtrustBenchmarkRunSummary.v0",
        "LabtrustReproducibilityCoverage.v0",
        "ReproducibilityBenchmarkManifest.v0",
        "HashStabilityReport.v0",
        "RegenerationReport.v0",
        "PcsBenchIngest.v0",
    }
)
_LABTRUST_EXTENDED_ARTIFACT_REF_ROLES = frozenset(
    {
        "native_report",
        "reproducibility_evidence",
        "regeneration_report",
        "canonical_ingest",
    }
)

# Paths that must appear in ingest ``artifact_refs`` for release-grade reproducibility.
RELEASE_GRADE_INGEST_REF_PATHS: frozenset[str] = frozenset(
    {
        "benchmark_run.v0.json",
        "coverage_report.v0.json",
        "benchmark_report.v0.json",
        "benchmark_manifest.v0.json",
        "hash_stability_report.v0.json",
        PCS_BENCH_INGEST_NAME,
    }
)


def build_release_reproducibility_coverage_report(
    *,
    run_doc: dict[str, Any],
    reproducibility_coverage: dict[str, Any],
    policy_root: Path,
) -> dict[str, Any]:
    """pcs-core ``CoverageReport.v0`` for release reproducibility from a benchmark run."""
    source_repo, source_commit = _benchmark_provenance(policy_root)
    aggregate = run_doc.get("aggregate") or {}
    runs = int(run_doc.get("runs") or 1)
    deterministic = bool(aggregate.get("command_deterministic"))
    numerator = float(runs if deterministic else 0)
    doc: dict[str, Any] = {
        "schema_version": "v0",
        "coverage_id": "labtrust-release-reproducibility-v0",
        "metric": "release_reproducibility_score",
        "metric_id": "release_reproducibility_score",
        "numerator": numerator,
        "denominator": float(runs),
        "coverage_ratio": numerator / float(runs) if runs else 0.0,
        "details": {
            "benchmark_id": run_doc.get("benchmark_id"),
            "mode": run_doc.get("mode"),
            "reproducibility_coverage": reproducibility_coverage,
        },
        "source_repo": source_repo,
        "source_commit": source_commit,
    }
    unsigned = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    doc["signature_or_digest"] = pcs_digest(unsigned)
    return doc


def build_benchmark_artifact_ref(
    *,
    artifact_type: str,
    path: str,
    embedded: dict[str, Any],
    source_repo: str,
    source_commit: str,
    role: str = "producer_export",
) -> dict[str, Any]:
    """BenchmarkArtifactRef.v0 for on-disk provenance of an embedded artifact."""
    content_digest = str(embedded.get("signature_or_digest") or pcs_digest(embedded))
    doc: dict[str, Any] = {
        "schema_version": "v0",
        "artifact_type": artifact_type,
        "path": path.replace("\\", "/"),
        "sha256": content_digest,
        "role": role,
        "source_repo": source_repo,
        "source_commit": source_commit,
    }
    unsigned = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    doc["signature_or_digest"] = pcs_digest(unsigned)
    return doc


def is_pcs_core_compatible_artifact_ref(ref: dict[str, Any]) -> bool:
    """True when ``ref`` validates under pcs-core ``BenchmarkArtifactRef.v0`` enums."""
    return (
        ref.get("artifact_type") in _PCS_CORE_ARTIFACT_REF_TYPES
        and ref.get("role") in _PCS_CORE_ARTIFACT_REF_ROLES
    )


def is_labtrust_extended_artifact_ref(ref: dict[str, Any]) -> bool:
    """True for LabTrust reproducibility sidecar refs (not pcs-core ingest schema enums)."""
    atype = ref.get("artifact_type")
    if atype not in _LABTRUST_EXTENDED_ARTIFACT_REF_TYPES:
        return False
    role = ref.get("role")
    if role in _LABTRUST_EXTENDED_ARTIFACT_REF_ROLES:
        return True
    return atype in (
        "LabtrustReproducibilityCoverage.v0",
        "ReproducibilityBenchmarkManifest.v0",
    ) and role in _PCS_CORE_ARTIFACT_REF_ROLES


def _load_json_artifact(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_pcs_core_reproducibility_artifact_refs(
    *,
    out_dir: Path,
    pcs_runs: list[dict[str, Any]],
    pcs_coverage: dict[str, Any],
    source_repo: str,
    source_commit: str,
    write_sidecars: bool = True,
) -> list[dict[str, Any]]:
    """
    pcs-core / pcs-bench compatible ``artifact_refs`` for embedded ingest objects.

    Writes one sidecar JSON per embedded ``BenchmarkRun.v0`` and ``CoverageReport.v0``
    under ``artifact_refs/`` so ``pcs-bench validate-ingest`` can match digests and paths.
    """
    out_dir = out_dir.resolve()
    refs: list[dict[str, Any]] = []
    runs_root = out_dir / "artifact_refs" / "benchmark_runs"
    cov_root = out_dir / "artifact_refs" / "coverage_reports"
    if write_sidecars:
        runs_root.mkdir(parents=True, exist_ok=True)
        cov_root.mkdir(parents=True, exist_ok=True)

    for run in pcs_runs:
        run_id = str(run["run_id"])
        rel = f"artifact_refs/benchmark_runs/{run_id}.v0.json"
        if write_sidecars:
            path = runs_root / f"{run_id}.v0.json"
            path.write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        refs.append(
            build_benchmark_artifact_ref(
                artifact_type="BenchmarkRun.v0",
                path=rel,
                embedded=run,
                source_repo=source_repo,
                source_commit=source_commit,
                role="producer_export",
            )
        )

    coverage_id = str(pcs_coverage.get("coverage_id", "coverage"))
    cov_rel = f"artifact_refs/coverage_reports/{coverage_id}.v0.json"
    if write_sidecars:
        cov_path = cov_root / f"{coverage_id}.v0.json"
        cov_path.write_text(
            json.dumps(pcs_coverage, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    refs.append(
        build_benchmark_artifact_ref(
            artifact_type="CoverageReport.v0",
            path=cov_rel,
            embedded=pcs_coverage,
            source_repo=source_repo,
            source_commit=source_commit,
            role="producer_export",
        )
    )
    return refs


def build_reproducibility_sidecar_artifact_refs(
    *,
    out_dir: Path,
    run_doc: dict[str, Any],
    pcs_coverage: dict[str, Any],
    benchmark_report: dict[str, Any],
    benchmark_manifest: dict[str, Any],
    source_repo: str,
    source_commit: str,
    benchmark_run_name: str = "benchmark_run.v0.json",
    coverage_report_name: str = "coverage_report.v0.json",
    benchmark_report_name: str = "benchmark_report.v0.json",
    benchmark_manifest_name: str = "benchmark_manifest.v0.json",
    hash_stability_report_name: str = "hash_stability_report.v0.json",
    regeneration_reports_dir: str = "regeneration_reports",
    labtrust_coverage_doc: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """BenchmarkArtifactRef.v0 entries for all reproducibility sidecar artifacts."""
    out_dir = out_dir.resolve()
    coverage_sidecar = labtrust_coverage_doc
    if coverage_sidecar is None:
        cov_path = out_dir / coverage_report_name
        if cov_path.is_file():
            coverage_sidecar = _load_json_artifact(cov_path)
        else:
            coverage_sidecar = pcs_coverage
    refs: list[dict[str, Any]] = [
        build_benchmark_artifact_ref(
            artifact_type="LabtrustBenchmarkRunSummary.v0",
            path=benchmark_run_name,
            embedded=run_doc,
            source_repo=source_repo,
            source_commit=source_commit,
            role="reproducibility_evidence",
        ),
        build_benchmark_artifact_ref(
            artifact_type="LabtrustReproducibilityCoverage.v0",
            path=coverage_report_name,
            embedded=coverage_sidecar,
            source_repo=source_repo,
            source_commit=source_commit,
            role="producer_export",
        ),
        build_benchmark_artifact_ref(
            artifact_type="BenchmarkReport.v0",
            path=benchmark_report_name,
            embedded=benchmark_report,
            source_repo=source_repo,
            source_commit=source_commit,
            role="native_report",
        ),
        build_benchmark_artifact_ref(
            artifact_type="ReproducibilityBenchmarkManifest.v0",
            path=benchmark_manifest_name,
            embedded=benchmark_manifest,
            source_repo=source_repo,
            source_commit=source_commit,
            role="producer_export",
        ),
    ]
    hash_path = out_dir / hash_stability_report_name
    if hash_path.is_file():
        hash_doc = _load_json_artifact(hash_path)
        refs.append(
            build_benchmark_artifact_ref(
                artifact_type="HashStabilityReport.v0",
                path=hash_stability_report_name,
                embedded=hash_doc,
                source_repo=source_repo,
                source_commit=source_commit,
                role="reproducibility_evidence",
            )
        )
    regen_dir = out_dir / regeneration_reports_dir
    if regen_dir.is_dir():
        for report_path in sorted(regen_dir.glob("run_*_regeneration_report.json")):
            rel = f"{regeneration_reports_dir}/{report_path.name}".replace("\\", "/")
            regen_doc = _load_json_artifact(report_path)
            refs.append(
                build_benchmark_artifact_ref(
                    artifact_type="RegenerationReport.v0",
                    path=rel,
                    embedded=regen_doc,
                    source_repo=source_repo,
                    source_commit=source_commit,
                    role="regeneration_report",
                )
            )
    return refs


def release_grade_flags(
    *,
    mode: str,
    per_run: list[dict[str, Any]],
    aggregate: dict[str, Any],
    pcs_core_configured: bool,
) -> tuple[bool, bool]:
    """Return ``(certifyedge_live, pcs_core_validation)`` for manifest emission."""
    certifyedge_live = mode == "full_regeneration"
    certifyedge_ok = float(aggregate.get("certifyedge_success_rate", 0.0)) >= 1.0
    pcs_ok = all(r.get("pcs_core_validation_passed") for r in per_run) if per_run else False
    return certifyedge_live and certifyedge_ok, pcs_core_configured and pcs_ok


def enforce_release_grade_gate(
    *,
    mode: str,
    runs: int,
    per_run: list[dict[str, Any]],
    aggregate: dict[str, Any],
    evidence_grade: str = EVIDENCE_GRADE_RELEASE,
    hash_stability_aggregate: dict[str, Any] | None = None,
) -> None:
    """Fail when release-grade semantics are not met."""
    if evidence_grade != EVIDENCE_GRADE_RELEASE:
        return
    if mode != "full_regeneration":
        raise ValueError("release-grade benchmark requires mode full_regeneration")
    if runs < 5:
        raise ValueError(f"release-grade benchmark requires runs >= 5, got {runs}")
    if float(aggregate.get("certifyedge_success_rate", 0.0)) < 1.0:
        raise ValueError(
            "release-grade benchmark requires certifyedge_call_success rate 1.0, "
            f"got {aggregate.get('certifyedge_success_rate')}"
        )
    stability = hash_stability_aggregate or aggregate
    if not stability.get("canonical_hashes_stable"):
        raise ValueError(
            "release-grade benchmark requires canonical_hashes_stable=true, "
            f"got {stability.get('canonical_hashes_stable')!r}"
        )
    if not stability.get("release_validation_stable"):
        raise ValueError(
            "release-grade benchmark requires release_validation_stable=true, "
            f"got {stability.get('release_validation_stable')!r}"
        )
    for run in per_run:
        if not run.get("release_protocol_validation_passed"):
            detail = run.get("release_protocol_validation_error") or (
                run.get("release_protocol_validation_checks") or "no checks"
            )
            raise ValueError(
                f"release-grade failed: run {run.get('run_index')} "
                f"release_protocol_validation_passed=false ({detail})"
            )
        if not run.get("status_policy_validation_passed"):
            raise ValueError(
                f"release-grade failed: run {run.get('run_index')} "
                "status_policy_validation_passed=false"
            )
        if not run.get("pcs_core_validation_passed"):
            raise ValueError(
                f"release-grade failed: run {run.get('run_index')} "
                "pcs_core_validation_passed=false (pcs-core schema validation)"
            )


def _certificate_status_for_run(run: dict[str, Any]) -> str:
    if not run.get("certifyedge_call_success", True):
        return "Rejected"
    if run.get("certificate_id"):
        return "CertificateChecked"
    return "not_applicable"


def build_pcs_core_benchmark_run_from_repro_iteration(
    *,
    run: dict[str, Any],
    task_id: str,
    case_id: str,
    mode: str,
    source_repo: str,
    source_commit: str,
) -> dict[str, Any]:
    """Map one LabTrust reproducibility iteration to pcs-core ``BenchmarkRun.v0``."""
    run_index = int(run["run_index"])
    release_ok = bool(run.get("release_protocol_validation_passed"))
    started = _REPRO_BASE_TIME + timedelta(seconds=run_index)
    completed = started + timedelta(milliseconds=max(int(run.get("duration_ms", 0)), 1))
    command = (
        f"labtrust benchmark-reproducibility --mode {mode} "
        f"--runs 1 --seed {run_index}"
    )
    artifacts = sorted(str(k) for k in (run.get("artifact_hashes") or {}))
    doc: dict[str, Any] = {
        "schema_version": "v0",
        "run_id": f"labtrust-repro-{mode}-run-{run_index}",
        "task_id": task_id,
        "case_id": case_id,
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "completed_at": completed.isoformat().replace("+00:00", "Z"),
        "commands": [{"command": command, "exit_code": 0 if release_ok else 1}],
        "artifacts_produced": artifacts,
        "observed_status": "passed" if release_ok else "failed",
        "observed_failure_code": None,
        "observed_responsible_component": None,
        "observed_repair_hint": None,
        "release_chain_status": "valid" if release_ok else "invalid",
        "certificate_status": _certificate_status_for_run(run),
        "duration_ms": int(run.get("duration_ms", 0)),
        "source_repo": source_repo,
        "source_commit": source_commit,
    }
    doc["signature_or_digest"] = _finalize_signature(doc)
    return doc


def build_pcs_core_benchmark_runs_from_reproducibility(
    *,
    per_run: list[dict[str, Any]],
    mode: str,
    policy_root: Path,
    task_id: str = REPRODUCIBILITY_TASK_ID,
    case_id: str = REPRODUCIBILITY_CASE_ID,
) -> list[dict[str, Any]]:
    """Build pcs-core ``BenchmarkRun.v0`` records for ``PcsBenchIngest.v0``."""
    source_repo, source_commit = _benchmark_provenance(policy_root)
    return [
        build_pcs_core_benchmark_run_from_repro_iteration(
            run=run,
            task_id=task_id,
            case_id=case_id,
            mode=mode,
            source_repo=source_repo,
            source_commit=source_commit,
        )
        for run in per_run
    ]


def build_pcs_bench_ingest(
    *,
    workflow_id: str,
    benchmark_runs: list[dict[str, Any]],
    coverage_reports: list[dict[str, Any]],
    policy_root: Path,
    suite_id: str = PCS_BENCH_SUITE_ID,
    failure_localization_reports: list[dict[str, Any]] | None = None,
    explain_quality_reports: list[dict[str, Any]] | None = None,
    profile_coverage_reports: list[dict[str, Any]] | None = None,
    commands: list[dict[str, Any]] | None = None,
    logs: list[str] | None = None,
    artifact_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_repo, source_commit = _benchmark_provenance(policy_root)
    doc: dict[str, Any] = {
        "schema_version": "v0",
        "producer_id": PRODUCER_ID,
        "suite_id": suite_id,
        "workflow_id": workflow_id,
        "benchmark_runs": list(benchmark_runs),
        "coverage_reports": list(coverage_reports),
        "failure_localization_reports": list(failure_localization_reports or []),
        "explain_quality_reports": list(explain_quality_reports or []),
        "profile_coverage_reports": list(profile_coverage_reports or []),
        "commands": list(commands or []),
        "logs": list(logs or []),
        "source_repo": source_repo,
        "source_commit": source_commit,
    }
    if artifact_refs:
        doc["artifact_refs"] = list(artifact_refs)
    unsigned = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    doc["signature_or_digest"] = pcs_digest(unsigned)
    return doc


def refresh_ingest_artifact_ref_digests(
    out_dir: Path,
    ingest: dict[str, Any],
    *,
    source_repo: str,
    source_commit: str,
) -> None:
    """Recompute ``artifact_refs[].sha256`` from on-disk JSON sidecars (after provenance edits)."""
    out_dir = out_dir.resolve()
    for ref in ingest.get("artifact_refs") or []:
        if not isinstance(ref, dict) or ref.get("role") == "canonical_ingest":
            continue
        rel = str(ref.get("path", "")).replace("\\", "/")
        sidecar = out_dir / rel
        if not sidecar.is_file():
            continue
        doc = json.loads(sidecar.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        digest = str(doc.get("signature_or_digest") or pcs_digest(doc))
        ref["sha256"] = digest
        ref["source_repo"] = source_repo
        ref["source_commit"] = source_commit
        unsigned = {k: v for k, v in ref.items() if k != "signature_or_digest"}
        ref["signature_or_digest"] = pcs_digest(unsigned)


def build_canonical_ingest_artifact_ref(
    *,
    ingest: dict[str, Any],
    ingest_path: str = PCS_BENCH_INGEST_NAME,
    source_repo: str,
    source_commit: str,
) -> dict[str, Any]:
    """BenchmarkArtifactRef for the on-disk ``pcs_bench_ingest.v0.json`` sidecar."""
    return build_benchmark_artifact_ref(
        artifact_type="PcsBenchIngest.v0",
        path=ingest_path.replace("\\", "/"),
        embedded=ingest,
        source_repo=source_repo,
        source_commit=source_commit,
        role="canonical_ingest",
    )


def merge_reproducibility_ingest_artifact_refs(
    *,
    pcs_core_refs: list[dict[str, Any]],
    sidecar_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Combine pcs-core embedded sidecars with LabTrust reproducibility evidence refs."""
    return list(pcs_core_refs) + list(sidecar_refs)


def build_reproducibility_benchmark_manifest(
    *,
    workflow_id: str,
    mode: str,
    runs: int,
    policy_root: Path,
    pcs_bench_ingest_path: str = PCS_BENCH_INGEST_NAME,
    suite_id: str = REPRODUCIBILITY_SUITE_ID,
    evidence_grade: str = EVIDENCE_GRADE_RELEASE,
    certifyedge_live: bool = False,
    pcs_core_validation: bool = False,
    canonical_hashes_stable: bool | None = None,
) -> dict[str, Any]:
    """Release-grade manifest for a reproducibility benchmark output directory."""
    source_repo, source_commit = _benchmark_provenance(policy_root)
    doc: dict[str, Any] = {
        "schema_version": "v0",
        "producer_id": PRODUCER_ID,
        "suite_id": suite_id,
        "workflow_id": workflow_id,
        "mode": mode,
        "runs": runs,
        "pcs_bench_ingest": pcs_bench_ingest_path.replace("\\", "/"),
        "evidence_grade": evidence_grade,
        "certifyedge_live": certifyedge_live,
        "pcs_core_validation": pcs_core_validation,
        "source_repo": source_repo,
        "source_commit": source_commit,
    }
    if canonical_hashes_stable is not None:
        doc["canonical_hashes_stable"] = canonical_hashes_stable
    unsigned = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    doc["signature_or_digest"] = pcs_digest(unsigned)
    return doc
