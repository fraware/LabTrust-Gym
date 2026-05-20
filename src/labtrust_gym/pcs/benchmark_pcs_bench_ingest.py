"""Build PcsBenchIngest.v0 exports for pcs-bench (aligned with pcs-core benchmark_compat)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.pcs.benchmark_case import LABTRUST_SOURCE_REPO, _benchmark_provenance
from labtrust_gym.pcs.benchmark_pcs_bench import PCS_BENCH_SUITE_ID
from labtrust_gym.pcs.hash import pcs_digest

PCS_BENCH_INGEST_NAME = "pcs_bench_ingest.v0.json"
PRODUCER_ID = "labtrust-gym"


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
    unsigned = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    doc["signature_or_digest"] = pcs_digest(unsigned)
    return doc
