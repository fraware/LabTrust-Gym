"""Reproducibility benchmark for LabTrust PCS release protocol generation."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.bench_schemas import (
    validate_benchmark_run,
    validate_hash_stability_report,
    validate_reproducibility_coverage_report,
)
from labtrust_gym.pcs.benchmark_case import LABTRUST_SOURCE_REPO, _benchmark_provenance
from labtrust_gym.pcs.benchmark_pcs_bench import PCS_BENCH_SUITE_ID
from labtrust_gym.pcs.benchmark_pcs_bench_ingest import (
    PCS_BENCH_INGEST_NAME,
    build_pcs_bench_ingest,
    build_release_reproducibility_coverage_report,
)
from labtrust_gym.pcs.hash import file_digest, pcs_digest
from labtrust_gym.pcs.regenerate_release_protocol import regenerate_release_protocol
from labtrust_gym.pcs.regeneration_report import REGENERATION_REPORT_NAME
from labtrust_gym.pcs.release_protocol_producer import LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS
from labtrust_gym.pcs.status_policy import check_release_status_policy
from labtrust_gym.pcs.verify_release_protocol import verify_release_protocol
from labtrust_gym.pcs.workflow_profile import workflow_profile_view

BENCHMARK_RUN_NAME = "benchmark_run.v0.json"
COVERAGE_REPORT_NAME = "coverage_report.v0.json"
HASH_STABILITY_REPORT_NAME = "hash_stability_report.v0.json"
REGENERATION_REPORTS_DIR = "regeneration_reports"

_HASH_ARTIFACTS = tuple(LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS) + (
    "manifest.json",
    "trace_certificate.json",
    "workflow_profile.v0.json",
    "regeneration_report.json",
)

_CANONICAL_JSON_ARTIFACTS = (
    "trace.json",
    "runtime_receipt.json",
    "science_claim_bundle.pending.json",
    "science_claim_bundle.certified.json",
    "trace_certificate.json",
    "handoff_to_certifyedge.json",
    "handoff_to_pf.json",
    "labtrust_release_fragment.json",
)


def _canonical_hashes(release_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in _CANONICAL_JSON_ARTIFACTS:
        path = release_dir / name
        if path.is_file():
            doc = json.loads(path.read_text(encoding="utf-8"))
            out[name] = pcs_digest(doc)
    return out


def _collect_release_metrics(
    release_dir: Path,
    *,
    pcs_core: Path | None,
    policy_root: Path,
    certifyedge_call_success: bool,
    regeneration_duration_ms: int = 0,
) -> dict[str, Any]:
    release_dir = release_dir.resolve()
    hashes: dict[str, str] = {}
    for name in _HASH_ARTIFACTS:
        path = release_dir / name
        if path.is_file():
            hashes[name] = file_digest(path)
    canonical = _canonical_hashes(release_dir)
    cert_id: str | None = None
    cert_path = release_dir / "trace_certificate.json"
    if cert_path.is_file():
        cert_id = json.loads(cert_path.read_text(encoding="utf-8")).get("certificate_id")

    t0 = time.perf_counter()
    release_checks: list[str] = []
    release_passed = False
    status_passed = False
    pcs_core_passed = False
    try:
        release_checks = verify_release_protocol(
            release_dir, pcs_core=pcs_core, policy_root=policy_root
        )
        release_passed = True
        pcs_core_passed = pcs_core is not None and any(
            c.startswith("release_sync") or "canonical" in c for c in release_checks
        )
        if pcs_core is None:
            pcs_core_passed = True
    except (ValueError, FileNotFoundError, RuntimeError):
        release_passed = False

    try:
        status_result = check_release_status_policy(release_dir)
        status_passed = status_result.get("status") == "passed"
    except (ValueError, FileNotFoundError):
        status_passed = False

    duration_ms = int((time.perf_counter() - t0) * 1000) + regeneration_duration_ms

    return {
        "artifact_hashes": hashes,
        "canonical_hashes": canonical,
        "certificate_id": cert_id,
        "certifyedge_call_success": certifyedge_call_success,
        "release_protocol_validation_passed": release_passed,
        "release_protocol_validation_checks": release_checks,
        "status_policy_validation_passed": status_passed,
        "pcs_core_validation_passed": pcs_core_passed,
        "regeneration_report_present": (release_dir / REGENERATION_REPORT_NAME).is_file(),
        "duration_ms": duration_ms,
        "regeneration_duration_ms": regeneration_duration_ms,
    }


def _full_regeneration_run(
    *,
    run_dir: Path,
    run_index: int,
    policy_root: Path,
    pcs_core: Path | None,
    certifyedge_bin: str,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    t0 = time.perf_counter()
    certifyedge_ok = True
    try:
        regenerate_release_protocol(
            run_dir,
            policy_root=policy_root,
            pcs_core=pcs_core,
            certifyedge_bin=certifyedge_bin,
        )
    except (FileNotFoundError, RuntimeError, OSError, ValueError) as exc:
        certifyedge_ok = False
        raise NotImplementedError(
            f"full_regeneration run {run_index} failed: {exc}"
        ) from exc
    regen_ms = int((time.perf_counter() - t0) * 1000)
    metrics = _collect_release_metrics(
        run_dir,
        pcs_core=pcs_core,
        policy_root=policy_root,
        certifyedge_call_success=certifyedge_ok,
        regeneration_duration_ms=regen_ms,
    )
    metrics["run_index"] = run_index
    metrics["run_dir"] = str(run_dir)
    return metrics


def _hash_stability_run(
    *,
    release_dir: Path,
    run_dir: Path,
    run_index: int,
    pcs_core: Path | None,
    policy_root: Path,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    if run_dir.exists():
        shutil.rmtree(run_dir)
    shutil.copytree(release_dir, run_dir)
    metrics = _collect_release_metrics(
        run_dir,
        pcs_core=pcs_core,
        policy_root=policy_root,
        certifyedge_call_success=True,
    )
    metrics["run_index"] = run_index
    metrics["run_dir"] = str(run_dir)
    return metrics


def _aggregate_runs(per_run: list[dict[str, Any]]) -> dict[str, Any]:
    if not per_run:
        raise ValueError("per_run must not be empty")
    first_hashes = per_run[0]["artifact_hashes"]
    first_canonical = per_run[0]["canonical_hashes"]
    hashes_stable = all(r["artifact_hashes"] == first_hashes for r in per_run)
    canonical_stable = all(r["canonical_hashes"] == first_canonical for r in per_run)
    cert_ids = [r.get("certificate_id") for r in per_run]
    cert_stable = len(set(cert_ids)) == 1
    release_stable = all(r.get("release_protocol_validation_passed") for r in per_run) and len(
        {tuple(r.get("release_protocol_validation_checks", [])) for r in per_run}
    ) == 1
    status_stable = all(r.get("status_policy_validation_passed") for r in per_run)
    pcs_stable = all(r.get("pcs_core_validation_passed") for r in per_run)
    certifyedge_rate = sum(1 for r in per_run if r.get("certifyedge_call_success")) / len(per_run)
    durations = [int(r["duration_ms"]) for r in per_run]
    deterministic = (
        hashes_stable
        and canonical_stable
        and release_stable
        and status_stable
        and pcs_stable
    )
    return {
        "artifact_hashes_stable": hashes_stable,
        "certificate_id_stable": cert_stable,
        "certificate_id_non_deterministic_declared": not cert_stable,
        "canonical_hashes_stable": canonical_stable,
        "release_validation_stable": release_stable,
        "status_policy_stable": status_stable,
        "pcs_core_validation_stable": pcs_stable,
        "certifyedge_success_rate": certifyedge_rate,
        "command_deterministic": deterministic,
        "duration_ms": {
            "min": min(durations),
            "max": max(durations),
            "mean": sum(durations) / len(durations),
        },
    }


def _benchmark_run_doc(
    *,
    profile_property_id: str,
    selected_mode: str,
    seed: int,
    runs: int,
    per_run: list[dict[str, Any]],
    aggregate: dict[str, Any],
) -> dict[str, Any]:
    slim_runs = []
    for r in per_run:
        slim_runs.append(
            {
                "run_index": r["run_index"],
                "duration_ms": r["duration_ms"],
                "artifact_hashes": r["artifact_hashes"],
                "certificate_id": r.get("certificate_id"),
                "release_validation_passed": r["release_protocol_validation_passed"],
                "release_validation_checks": r.get("release_protocol_validation_checks", []),
            }
        )
    slim_aggregate = {
        k: aggregate[k]
        for k in (
            "artifact_hashes_stable",
            "certificate_id_stable",
            "certificate_id_non_deterministic_declared",
            "canonical_hashes_stable",
            "release_validation_stable",
            "command_deterministic",
            "duration_ms",
        )
    }
    return {
        "schema_version": "v0",
        "benchmark_id": "labtrust-reproducibility-v0",
        "workflow_id": profile_property_id,
        "mode": selected_mode,
        "seed": seed,
        "runs": runs,
        "per_run": slim_runs,
        "aggregate": slim_aggregate,
    }


def _hash_stability_report_doc(
    *,
    profile_property_id: str,
    seed: int,
    runs: int,
    per_run: list[dict[str, Any]],
    aggregate: dict[str, Any],
    policy_root: Path,
) -> dict[str, Any]:
    source_repo, source_commit = _benchmark_provenance(policy_root)
    doc: dict[str, Any] = {
        "schema_version": "v0",
        "benchmark_id": "labtrust-hash-stability-v0",
        "workflow_id": profile_property_id,
        "runs": runs,
        "seed": seed,
        "per_run": per_run,
        "aggregate": aggregate,
        "source_repo": source_repo,
        "source_commit": source_commit,
    }
    unsigned = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    doc["signature_or_digest"] = pcs_digest(unsigned)
    return doc


def _write_regeneration_reports(out_dir: Path, per_run: list[dict[str, Any]]) -> None:
    reports_dir = out_dir / REGENERATION_REPORTS_DIR
    if reports_dir.exists():
        shutil.rmtree(reports_dir)
    reports_dir.mkdir(parents=True)
    for run in per_run:
        run_dir = Path(run["run_dir"])
        src = run_dir / REGENERATION_REPORT_NAME
        if src.is_file():
            dest = reports_dir / f"run_{run['run_index']}_{REGENERATION_REPORT_NAME}"
            shutil.copy2(src, dest)


def benchmark_reproducibility(
    out_dir: Path,
    *,
    workflow_key: str,
    policy_root: Path,
    release_dir: Path | None = None,
    pcs_core: Path | None = None,
    certifyedge_bin: str = "certifyedge",
    runs: int = 5,
    seed: int = 42,
    mode: str | None = None,
    include_hash_stability: bool = True,
) -> dict[str, Any]:
    """
    Measure release-chain reproducibility (release-grade default: full_regeneration).

    Writes ``benchmark_run.v0.json``, ``coverage_report.v0.json``,
    ``regeneration_reports/``, and ``hash_stability_report.v0.json`` (when enabled).
    """
    if runs < 1:
        raise ValueError("runs must be >= 1")
    profile = workflow_profile_view(policy_root=policy_root)
    release = release_dir or (policy_root / "examples" / "pcs_qc_release" / "release")
    if not (release / "trace.json").is_file():
        raise FileNotFoundError(f"release baseline not found: {release}")

    selected_mode = mode or "full_regeneration"
    if selected_mode not in ("hash_stability", "full_regeneration"):
        raise ValueError(f"unsupported mode {selected_mode!r}")

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_root = out_dir / "runs"
    if runs_root.exists():
        shutil.rmtree(runs_root)
    runs_root.mkdir()

    per_run: list[dict[str, Any]] = []
    if selected_mode == "hash_stability":
        for i in range(runs):
            per_run.append(
                _hash_stability_run(
                    release_dir=release,
                    run_dir=runs_root / f"run_{i}",
                    run_index=i,
                    pcs_core=pcs_core,
                    policy_root=policy_root,
                )
            )
    else:
        for i in range(runs):
            per_run.append(
                _full_regeneration_run(
                    run_dir=runs_root / f"run_{i}",
                    run_index=i,
                    policy_root=policy_root,
                    pcs_core=pcs_core,
                    certifyedge_bin=certifyedge_bin,
                )
            )

    aggregate = _aggregate_runs(per_run)
    run_doc = _benchmark_run_doc(
        profile_property_id=profile.property_id,
        selected_mode=selected_mode,
        seed=seed,
        runs=runs,
        per_run=per_run,
        aggregate=aggregate,
    )
    validate_benchmark_run(run_doc)
    (out_dir / BENCHMARK_RUN_NAME).write_text(
        json.dumps(run_doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if selected_mode == "full_regeneration":
        _write_regeneration_reports(out_dir, per_run)

    if include_hash_stability and selected_mode == "full_regeneration":
        hash_runs_root = out_dir / "hash_stability_runs"
        if hash_runs_root.exists():
            shutil.rmtree(hash_runs_root)
        hash_runs_root.mkdir()
        hash_per_run: list[dict[str, Any]] = []
        for i in range(runs):
            hash_per_run.append(
                _hash_stability_run(
                    release_dir=release,
                    run_dir=hash_runs_root / f"run_{i}",
                    run_index=i,
                    pcs_core=pcs_core,
                    policy_root=policy_root,
                )
            )
        hash_aggregate = _aggregate_runs(hash_per_run)
        hash_doc = _hash_stability_report_doc(
            profile_property_id=profile.property_id,
            seed=seed,
            runs=runs,
            per_run=hash_per_run,
            aggregate=hash_aggregate,
            policy_root=policy_root,
        )
        validate_hash_stability_report(hash_doc)
        (out_dir / HASH_STABILITY_REPORT_NAME).write_text(
            json.dumps(hash_doc, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    coverage = {
        "schema_version": "v0",
        "workflow_id": profile.property_id,
        "task_id": "labtrust-qc-release-reproducibility-v0",
        "reproducibility_passed": aggregate["command_deterministic"],
        "runs": runs,
        "mode": selected_mode,
    }
    if include_hash_stability and (out_dir / HASH_STABILITY_REPORT_NAME).is_file():
        hash_report = json.loads((out_dir / HASH_STABILITY_REPORT_NAME).read_text(encoding="utf-8"))
        coverage["hash_stability_passed"] = hash_report["aggregate"]["command_deterministic"]
    validate_reproducibility_coverage_report(coverage)
    (out_dir / COVERAGE_REPORT_NAME).write_text(
        json.dumps(coverage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    pcs_coverage = build_release_reproducibility_coverage_report(
        run_doc=run_doc,
        reproducibility_coverage=coverage,
        policy_root=policy_root,
    )
    ingest = build_pcs_bench_ingest(
        workflow_id=workflow_key,
        benchmark_runs=[run_doc],
        coverage_reports=[pcs_coverage],
        policy_root=policy_root,
        suite_id=PCS_BENCH_SUITE_ID,
        commands=[
            {
                "command": (
                    f"labtrust benchmark-reproducibility --workflow {workflow_key} "
                    f"--mode {selected_mode} --runs {runs} --out {out_dir}"
                ),
                "exit_code": 0 if aggregate["command_deterministic"] else 1,
            }
        ],
        logs=[f"mode={selected_mode} deterministic={aggregate['command_deterministic']}"],
    )
    if pcs_core is not None:
        from labtrust_gym.pcs.bench_schemas import validate_pcs_bench_ingest_pcs_core

        validate_pcs_bench_ingest_pcs_core(ingest, pcs_core_root=pcs_core)
    (out_dir / PCS_BENCH_INGEST_NAME).write_text(
        json.dumps(ingest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return run_doc
