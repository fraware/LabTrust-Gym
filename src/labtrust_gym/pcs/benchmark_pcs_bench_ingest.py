"""Build PcsBenchIngest.v0 exports for pcs-bench (aligned with pcs-core benchmark_compat)."""

from __future__ import annotations

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
PRODUCER_ID = "labtrust-gym"
REPRODUCIBILITY_SUITE_ID = "labtrust-qc-reproducibility-v0"
REPRODUCIBILITY_TASK_ID = "labtrust-qc-release-reproducibility-v0"
REPRODUCIBILITY_CASE_ID = "labtrust-valid-release-v0"
_REPRO_BASE_TIME = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)


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


def build_reproducibility_benchmark_manifest(
    *,
    workflow_id: str,
    mode: str,
    runs: int,
    policy_root: Path,
    pcs_bench_ingest_path: str = PCS_BENCH_INGEST_NAME,
    suite_id: str = REPRODUCIBILITY_SUITE_ID,
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
        "source_repo": source_repo,
        "source_commit": source_commit,
    }
    unsigned = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    doc["signature_or_digest"] = pcs_digest(unsigned)
    return doc
