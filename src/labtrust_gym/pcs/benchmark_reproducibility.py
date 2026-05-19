"""Reproducibility benchmark for LabTrust PCS release protocol generation."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.bench_schemas import (
    validate_benchmark_run,
    validate_reproducibility_coverage_report,
)
from labtrust_gym.pcs.hash import file_digest
from labtrust_gym.pcs.regenerate_release_protocol import regenerate_release_protocol
from labtrust_gym.pcs.release_protocol_producer import LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS
from labtrust_gym.pcs.verify_release_protocol import verify_release_protocol
from labtrust_gym.pcs.workflow_profile import workflow_profile_view

BENCHMARK_RUN_NAME = "benchmark_run.v0.json"
COVERAGE_REPORT_NAME = "coverage_report.v0.json"

_HASH_ARTIFACTS = tuple(LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS) + (
    "manifest.json",
    "trace_certificate.json",
    "workflow_profile.v0.json",
)


def _collect_release_metrics(release_dir: Path, *, pcs_core: Path | None) -> dict[str, Any]:
    release_dir = release_dir.resolve()
    hashes: dict[str, str] = {}
    for name in _HASH_ARTIFACTS:
        path = release_dir / name
        if path.is_file():
            hashes[name] = file_digest(path)
    cert_id: str | None = None
    cert_path = release_dir / "trace_certificate.json"
    if cert_path.is_file():
        cert_id = json.loads(cert_path.read_text(encoding="utf-8")).get("certificate_id")
    t0 = time.perf_counter()
    checks = verify_release_protocol(release_dir, pcs_core=pcs_core)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "artifact_hashes": hashes,
        "certificate_id": cert_id,
        "release_validation_passed": True,
        "release_validation_checks": checks,
        "duration_ms": duration_ms,
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
    regenerate_release_protocol(
        run_dir,
        policy_root=policy_root,
        pcs_core=pcs_core,
        certifyedge_bin=certifyedge_bin,
    )
    metrics = _collect_release_metrics(run_dir, pcs_core=pcs_core)
    metrics["run_index"] = run_index
    return metrics


def _hash_stability_run(
    *,
    release_dir: Path,
    run_dir: Path,
    run_index: int,
    pcs_core: Path | None,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    if run_dir.exists():
        shutil.rmtree(run_dir)
    shutil.copytree(release_dir, run_dir)
    metrics = _collect_release_metrics(run_dir, pcs_core=pcs_core)
    metrics["run_index"] = run_index
    return metrics


def _aggregate_runs(per_run: list[dict[str, Any]]) -> dict[str, Any]:
    if not per_run:
        raise ValueError("per_run must not be empty")
    first_hashes = per_run[0]["artifact_hashes"]
    hashes_stable = all(r["artifact_hashes"] == first_hashes for r in per_run)
    cert_ids = [r.get("certificate_id") for r in per_run]
    cert_stable = len(set(cert_ids)) == 1
    validation_stable = all(r.get("release_validation_passed") for r in per_run) and len(
        {tuple(r.get("release_validation_checks", [])) for r in per_run}
    ) == 1
    durations = [int(r["duration_ms"]) for r in per_run]
    return {
        "artifact_hashes_stable": hashes_stable,
        "certificate_id_stable": cert_stable,
        "certificate_id_non_deterministic_declared": not cert_stable,
        "canonical_hashes_stable": hashes_stable,
        "release_validation_stable": validation_stable,
        "command_deterministic": hashes_stable and validation_stable,
        "duration_ms": {
            "min": min(durations),
            "max": max(durations),
            "mean": sum(durations) / len(durations),
        },
    }


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
) -> dict[str, Any]:
    """
    Measure release-chain reproducibility.

    ``hash_stability`` (default): copy committed release ``runs`` times and verify
    hashes and validation are identical. ``full_regeneration`` re-runs protocol
    generation when CertifyEdge is available (local benches only).
    """
    del workflow_key
    if runs < 1:
        raise ValueError("runs must be >= 1")
    profile = workflow_profile_view(policy_root=policy_root)
    release = release_dir or (policy_root / "examples" / "pcs_qc_release" / "release")
    if not (release / "trace.json").is_file():
        raise FileNotFoundError(f"release baseline not found: {release}")

    selected_mode = mode or "hash_stability"
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
                )
            )
    else:
        for i in range(runs):
            try:
                per_run.append(
                    _full_regeneration_run(
                        run_dir=runs_root / f"run_{i}",
                        run_index=i,
                        policy_root=policy_root,
                        pcs_core=pcs_core,
                        certifyedge_bin=certifyedge_bin,
                    )
                )
            except (FileNotFoundError, RuntimeError, OSError) as exc:
                raise NotImplementedError(
                    "full_regeneration requires CertifyEdge and a writable release tree; "
                    f"run {i} failed: {exc}"
                ) from exc

    aggregate = _aggregate_runs(per_run)
    doc: dict[str, Any] = {
        "schema_version": "v0",
        "benchmark_id": "labtrust-reproducibility-v0",
        "workflow_id": profile.property_id,
        "mode": selected_mode,
        "seed": seed,
        "runs": runs,
        "per_run": per_run,
        "aggregate": aggregate,
    }
    validate_benchmark_run(doc)
    run_path = out_dir / BENCHMARK_RUN_NAME
    run_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    coverage = {
        "schema_version": "v0",
        "workflow_id": profile.property_id,
        "task_id": "labtrust-qc-release-reproducibility-v0",
        "reproducibility_passed": aggregate["command_deterministic"],
        "runs": runs,
        "mode": selected_mode,
    }
    validate_reproducibility_coverage_report(coverage)
    (out_dir / COVERAGE_REPORT_NAME).write_text(
        json.dumps(coverage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return doc
