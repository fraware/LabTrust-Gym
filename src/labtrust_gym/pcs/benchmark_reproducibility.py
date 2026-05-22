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
from labtrust_gym.pcs.benchmark_pcs_bench_ingest import (
    EVIDENCE_GRADE_DEVELOPER,
    EVIDENCE_GRADE_RELEASE,
    PCS_BENCH_INGEST_NAME,
    REPRODUCIBILITY_SUITE_ID,
    build_pcs_bench_ingest,
    build_pcs_core_benchmark_runs_from_reproducibility,
    build_release_reproducibility_coverage_report,
    LABTRUST_EXTENDED_ARTIFACT_REFS_NAME,
    build_pcs_core_reproducibility_artifact_refs,
    build_canonical_ingest_artifact_ref,
    build_reproducibility_benchmark_manifest,
    build_reproducibility_sidecar_artifact_refs,
    enforce_release_grade_gate,
    merge_reproducibility_ingest_artifact_refs,
    release_grade_flags,
)
from labtrust_gym.pcs.workflow_profile import canonical_workflow_property_id
from labtrust_gym.pcs.benchmark_report import (
    BENCHMARK_REPORT_NAME,
    build_reproducibility_pcs_benchmark_report,
)
from labtrust_gym.pcs.hash import file_digest, pcs_digest
from labtrust_gym.pcs.regenerate_release_protocol import regenerate_release_protocol
from labtrust_gym.pcs.regeneration_report import REGENERATION_REPORT_NAME
from labtrust_gym.pcs.release_protocol_producer import LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS
from labtrust_gym.pcs.status_policy import check_release_status_policy
from labtrust_gym.pcs.verify_release_protocol import verify_release_protocol
from labtrust_gym.pcs.workflow_profile import workflow_profile_view

BENCHMARK_RUN_NAME = "benchmark_run.v0.json"
BENCHMARK_MANIFEST_NAME = "benchmark_manifest.v0.json"
COVERAGE_REPORT_NAME = "coverage_report.v0.json"
HASH_STABILITY_REPORT_NAME = "hash_stability_report.v0.json"


def _portable_command_out(out_dir: Path, policy_root: Path) -> str:
    """Repo-relative POSIX path for ingest commands (portable across OS/CI)."""
    out_resolved = out_dir.resolve()
    for base in (policy_root.resolve(), Path.cwd().resolve()):
        try:
            return out_resolved.relative_to(base).as_posix()
        except ValueError:
            continue
    return out_resolved.as_posix()
REGENERATION_REPORTS_DIR = "regeneration_reports"


class RegenerationUnavailableError(NotImplementedError):
    """CertifyEdge or regenerate-release-protocol unavailable (CI may fall back)."""


from labtrust_gym.pcs.bench_schemas import resolve_pcs_core_schema_root

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
    release_error: str | None = None
    try:
        release_checks = verify_release_protocol(
            release_dir,
            pcs_core=pcs_core,
            policy_root=policy_root,
            compare_canonical=False,
        )
        release_passed = True
        if pcs_core is not None:
            pcs_core_passed = any(c.startswith("schema_validate") for c in release_checks)
        else:
            pcs_core_passed = True
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        release_passed = False
        release_error = str(exc)

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
        "release_protocol_validation_error": release_error,
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
        raise RegenerationUnavailableError(
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
    doc: dict[str, Any] = {
        "schema_version": "v0",
        "benchmark_id": "labtrust-reproducibility-v0",
        "workflow_id": profile_property_id,
        "mode": selected_mode,
        "seed": seed,
        "runs": runs,
        "per_run": slim_runs,
        "aggregate": slim_aggregate,
    }
    unsigned = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    doc["signature_or_digest"] = pcs_digest(unsigned)
    return doc


def _hash_stability_report_doc(
    *,
    profile_property_id: str,
    seed: int,
    runs: int,
    per_run: list[dict[str, Any]],
    aggregate: dict[str, Any],
    policy_root: Path,
) -> dict[str, Any]:
    del policy_root
    doc: dict[str, Any] = {
        "schema_version": "v0",
        "benchmark_id": "labtrust-hash-stability-v0",
        "workflow_id": profile_property_id,
        "runs": runs,
        "seed": seed,
        "per_run": per_run,
        "aggregate": aggregate,
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
    validate_pcs_core_output: Path | None = None,
    release_grade: bool | None = None,
) -> dict[str, Any]:
    """
    Measure release-chain reproducibility (release-grade default: full_regeneration).

    Writes ``benchmark_run.v0.json``, ``coverage_report.v0.json``,
    ``benchmark_manifest.v0.json``, ``pcs_bench_ingest.v0.json``,
    ``benchmark_report.v0.json``, ``regeneration_reports/``, and
    ``hash_stability_report.v0.json`` (when enabled).
    """
    if runs < 1:
        raise ValueError("runs must be >= 1")
    profile = workflow_profile_view(policy_root=policy_root)
    workflow_id = canonical_workflow_property_id(workflow_key, profile=profile)
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
        profile_property_id=workflow_id,
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

    hash_stability_aggregate: dict[str, Any] | None = None
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
        hash_stability_aggregate = hash_aggregate
        hash_doc = _hash_stability_report_doc(
            profile_property_id=workflow_id,
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
        "workflow_id": workflow_id,
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
    pcs_runs = build_pcs_core_benchmark_runs_from_reproducibility(
        per_run=per_run,
        mode=selected_mode,
        policy_root=policy_root,
    )
    source_repo, source_commit = _benchmark_provenance(policy_root)
    schema_root = resolve_pcs_core_schema_root(validate_pcs_core_output or pcs_core)
    pcs_core_configured = schema_root is not None
    if release_grade is False:
        grade = EVIDENCE_GRADE_DEVELOPER
    elif release_grade is True or selected_mode == "full_regeneration":
        grade = EVIDENCE_GRADE_RELEASE
    else:
        grade = EVIDENCE_GRADE_DEVELOPER
    if grade == EVIDENCE_GRADE_RELEASE:
        enforce_release_grade_gate(
            mode=selected_mode,
            runs=runs,
            per_run=per_run,
            aggregate=aggregate,
            evidence_grade=grade,
            hash_stability_aggregate=hash_stability_aggregate,
        )
    certifyedge_live, pcs_core_validation = release_grade_flags(
        mode=selected_mode,
        per_run=per_run,
        aggregate=aggregate,
        pcs_core_configured=pcs_core_configured,
    )

    benchmark_report = build_reproducibility_pcs_benchmark_report(
        pcs_runs=pcs_runs,
        pcs_coverage=pcs_coverage,
        aggregate=aggregate,
        policy_root=policy_root,
    )
    (out_dir / BENCHMARK_REPORT_NAME).write_text(
        json.dumps(benchmark_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest = build_reproducibility_benchmark_manifest(
        workflow_id=workflow_id,
        mode=selected_mode,
        runs=runs,
        policy_root=policy_root,
        evidence_grade=grade,
        certifyedge_live=certifyedge_live,
        pcs_core_validation=pcs_core_validation,
        canonical_hashes_stable=bool(
            (hash_stability_aggregate or aggregate).get("canonical_hashes_stable")
        )
        if grade == EVIDENCE_GRADE_RELEASE
        else None,
    )
    from labtrust_gym.pcs.bench_schemas import validate_reproducibility_benchmark_manifest

    validate_reproducibility_benchmark_manifest(manifest, policy_root=policy_root)

    pcs_artifact_refs = build_pcs_core_reproducibility_artifact_refs(
        out_dir=out_dir,
        pcs_runs=pcs_runs,
        pcs_coverage=pcs_coverage,
        source_repo=source_repo,
        source_commit=source_commit,
        write_sidecars=True,
    )
    labtrust_coverage_doc = json.loads(
        (out_dir / COVERAGE_REPORT_NAME).read_text(encoding="utf-8")
    )
    labtrust_artifact_refs = build_reproducibility_sidecar_artifact_refs(
        out_dir=out_dir,
        run_doc=run_doc,
        pcs_coverage=pcs_coverage,
        benchmark_report=benchmark_report,
        benchmark_manifest=manifest,
        source_repo=source_repo,
        source_commit=source_commit,
        benchmark_run_name=BENCHMARK_RUN_NAME,
        coverage_report_name=COVERAGE_REPORT_NAME,
        benchmark_report_name=BENCHMARK_REPORT_NAME,
        benchmark_manifest_name=BENCHMARK_MANIFEST_NAME,
        hash_stability_report_name=HASH_STABILITY_REPORT_NAME,
        regeneration_reports_dir=REGENERATION_REPORTS_DIR,
        labtrust_coverage_doc=labtrust_coverage_doc,
    )
    (out_dir / LABTRUST_EXTENDED_ARTIFACT_REFS_NAME).write_text(
        json.dumps(
            {
                "schema_version": "v0",
                "producer_id": "labtrust-gym",
                "artifact_refs": labtrust_artifact_refs,
                "source_repo": source_repo,
                "source_commit": source_commit,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    ingest = build_pcs_bench_ingest(
        workflow_id=workflow_id,
        benchmark_runs=pcs_runs,
        coverage_reports=[pcs_coverage],
        policy_root=policy_root,
        suite_id=REPRODUCIBILITY_SUITE_ID,
        artifact_refs=merge_reproducibility_ingest_artifact_refs(
            pcs_core_refs=pcs_artifact_refs,
            sidecar_refs=labtrust_artifact_refs,
        ),
        commands=[
            {
                "command": (
                    f"labtrust benchmark-reproducibility --workflow {workflow_id} "
                    f"--mode {selected_mode} --runs {runs} "
                    f"--out {_portable_command_out(out_dir, policy_root)}"
                ),
                "exit_code": 0 if aggregate["command_deterministic"] else 1,
            }
        ],
        logs=[f"mode={selected_mode} deterministic={aggregate['command_deterministic']}"],
    )
    pre_canonical_digest = str(ingest["signature_or_digest"])
    ingest["artifact_refs"].append(
        build_canonical_ingest_artifact_ref(
            ingest={"signature_or_digest": pre_canonical_digest},
            source_repo=source_repo,
            source_commit=source_commit,
        )
    )
    unsigned_ingest = {k: v for k, v in ingest.items() if k != "signature_or_digest"}
    ingest["signature_or_digest"] = pcs_digest(unsigned_ingest)
    (out_dir / PCS_BENCH_INGEST_NAME).write_text(
        json.dumps(ingest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    from labtrust_gym.pcs.bench_schemas import validate_pcs_bench_ingest

    validate_pcs_bench_ingest(ingest, policy_root=policy_root)

    (out_dir / BENCHMARK_MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if schema_root is not None:
        from labtrust_gym.pcs.bench_schemas import (
            validate_benchmark_report_pcs_core,
            validate_benchmark_run_pcs_core,
            validate_coverage_report_pcs_core,
            validate_pcs_bench_ingest_pcs_core,
        )

        validate_pcs_bench_ingest_pcs_core(ingest, pcs_core_root=schema_root)
        validate_coverage_report_pcs_core(pcs_coverage, pcs_core_root=schema_root)
        validate_benchmark_report_pcs_core(benchmark_report, pcs_core_root=schema_root)
        for run in pcs_runs:
            validate_benchmark_run_pcs_core(run, pcs_core_root=schema_root)

    if validate_pcs_core_output is not None:
        if schema_root is None:
            raise FileNotFoundError(
                f"pcs-core schemas not found at {validate_pcs_core_output.resolve()}"
            )
        from labtrust_gym.pcs.bench_schemas import validate_pcs_core_reproducibility_outputs

        validate_pcs_core_reproducibility_outputs(
            out_dir,
            pcs_core_root=schema_root,
            policy_root=policy_root,
        )

    return run_doc
