"""BenchmarkCase.v0 builders (pcs-core aligned) and LabTrust localization metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.bench_schemas import validate_benchmark_case
from labtrust_gym.pcs.hash import pcs_digest
from labtrust_gym.pcs.manifest import _git_head

BENCHMARK_CASE_NAME = "benchmark_case.v0.json"
LABTRUST_EXTENSION_NAME = "labtrust_benchmark_extension.v0.json"
BENCHMARK_TASK_ID = "labtrust-qc-release-v0"
LABTRUST_SOURCE_REPO = "https://github.com/fraware/LabTrust-Gym"
VALID_RELEASE_DIR_NAME = "valid_release"
INPUT_ARTIFACTS_DIR = "input_artifacts"
PCS_BENCH_RELEASE_DIRECTORY = "input_artifacts/"
EXPECTED_FAILURE_NAME = "expected_failure.json"
EXPECTED_REPAIR_HINT_NAME = "expected_repair_hint.json"

_ARTIFACT_TYPE_BY_BASENAME: dict[str, str] = {
    "trace.json": "LabTrustTrace.v0",
    "runtime_receipt.json": "RuntimeReceipt.v0",
    "science_claim_bundle.pending.json": "ScienceClaimBundle.v0",
    "science_claim_bundle.certified.json": "ScienceClaimBundle.v0",
    "trace_certificate.json": "TraceCertificate.v0",
    "handoff_to_certifyedge.json": "HandoffManifest.v0",
    "handoff_to_pf.json": "HandoffManifest.v0",
    "labtrust_release_fragment.json": "ComponentReleaseFragment.v0",
    "workflow_profile.v0.json": "WorkflowProfile.v0",
    "manifest.json": "ReleaseManifest.v0",
    "verification_result.json": "VerificationResult.v0",
    "signed_science_claim_bundle.json": "SignedScienceClaimBundle.v0",
    "regeneration_report.json": "RegenerationReport.v0",
    "proof_obligation_hints.json": "ProofObligationHints.v0",
    "proof_obligation_identifiers.json": "ProofObligationIdentifiers.v0",
    "formalization_readiness_report.json": "FormalizationReadinessReport.v0",
    "trace_hash_alignment.json": "TraceHashAlignment.v0",
    "run_meta.json": "RunMeta.v0",
}


@dataclass(frozen=True)
class BenchmarkLocalization:
    pcs_case_kind: str
    benchmark_failure_code: str
    pcs_expected_status: str
    pcs_repair_hint_kind: str
    pcs_responsible_component: str
    detection_layer: str
    repair_command: str
    operator_hint: str
    operator_repair_hint_kind: str | None = None

    @property
    def repair_hint_kind_for_fixture(self) -> str:
        return self.operator_repair_hint_kind or self.pcs_repair_hint_kind


def benchmark_case_id_for(gallery_case_id: str) -> str:
    slug = gallery_case_id.replace("_", "-")
    return f"labtrust-{slug}-v0"


def _artifact_refs(artifact_names: list[str]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for name in sorted(artifact_names):
        refs.append(
            {
                "path": name,
                "artifact_type": _ARTIFACT_TYPE_BY_BASENAME.get(name, "Unknown.v0"),
                "role": name.replace(".", "_"),
            }
        )
    return refs


def _benchmark_provenance(policy_root: Path) -> tuple[str, str]:
    commit = _git_head(policy_root)
    if len(commit) != 40:
        raise ValueError(f"expected 40-char git commit for benchmark case, got {commit!r}")
    return LABTRUST_SOURCE_REPO, commit


def _finalize_signature(doc: dict[str, Any]) -> str:
    unsigned = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    return pcs_digest(unsigned)


SYSTEM_OUTCOME_BY_CASE_KIND: dict[str, str] = {
    "valid_release": "admitted",
    "invalid_certificate": "rejected",
    "invalid_hash_mismatch": "rejected",
    "invalid_handoff": "rejected",
    "invalid_registry": "rejected",
    "invalid_formal_check": "formal_failed",
    "invalid_import": "import_failed",
    "invalid_render": "render_failed",
    "stale_release": "stale",
}


def expected_system_outcome_for(case_kind: str) -> str:
    try:
        return SYSTEM_OUTCOME_BY_CASE_KIND[case_kind]
    except KeyError as exc:
        raise ValueError(f"no system outcome for case_kind {case_kind!r}") from exc


PCS_CASE_KIND_BY_GALLERY: dict[str, str] = {
    "valid_release": "valid_release",
    "missing_qc_result": "invalid_render",
    "unauthorized_release": "invalid_render",
    "trace_hash_tamper": "invalid_hash_mismatch",
    "certificate_id_tamper": "invalid_certificate",
    "stale_trace_after_certificate": "stale_release",
    "legacy_handoff_file": "invalid_handoff",
    "placeholder_commit": "invalid_registry",
    "lean_trace_hash_mismatch": "invalid_formal_check",
    "lean_rejected_certificate": "invalid_formal_check",
    "lean_stale_certificate": "invalid_formal_check",
    "lean_signed_hash_mismatch": "invalid_formal_check",
    "scientific_memory_import_failure": "invalid_import",
}

_LOCALIZATION_BY_GALLERY: dict[str, BenchmarkLocalization] = {
    "missing_qc_result": BenchmarkLocalization(
        pcs_case_kind="invalid_render",
        benchmark_failure_code="missing_qc",
        pcs_expected_status="failed",
        pcs_repair_hint_kind="unknown",
        pcs_responsible_component="runtime_producer",
        detection_layer="LabTrust",
        repair_command=(
            "labtrust run-demo qc-release --deterministic --out <run_dir> "
            "&& labtrust export-runtime-receipt --run <run_dir> --out runtime_receipt.json"
        ),
        operator_hint="Complete the QC verification step before release_sample.",
    ),
    "unauthorized_release": BenchmarkLocalization(
        pcs_case_kind="invalid_render",
        benchmark_failure_code="unauthorized_release",
        pcs_expected_status="failed",
        pcs_repair_hint_kind="unknown",
        pcs_responsible_component="runtime_producer",
        detection_layer="LabTrust",
        repair_command="labtrust run-demo qc-release --deterministic --out <run_dir>",
        operator_hint="Use an authorized actor role for release_sample.",
    ),
    "trace_hash_tamper": BenchmarkLocalization(
        pcs_case_kind="invalid_hash_mismatch",
        benchmark_failure_code="trace_hash_mismatch",
        pcs_expected_status="failed",
        pcs_repair_hint_kind="align_hash",
        pcs_responsible_component="runtime_producer",
        detection_layer="LabTrust",
        repair_command=(
            "labtrust regenerate-release-protocol --pcs-core ../pcs-core "
            "--certifyedge-bin certifyedge --out examples/pcs_qc_release/release"
        ),
        operator_hint="Regenerate trace.json from the workflow run; do not edit trace_hash in isolation.",
        operator_repair_hint_kind="regenerate_trace_or_certificate",
    ),
    "certificate_id_tamper": BenchmarkLocalization(
        pcs_case_kind="invalid_certificate",
        benchmark_failure_code="certificate_id_mismatch",
        pcs_expected_status="failed",
        pcs_repair_hint_kind="align_certificate_id",
        pcs_responsible_component="certificate_producer",
        detection_layer="CertifyEdge",
        repair_command=(
            "certifyedge emit-pcs-certificate ... && labtrust attach-certificate "
            "--bundle science_claim_bundle.pending.json --certificate trace_certificate.json"
        ),
        operator_hint="Re-run CertifyEdge emit-pcs-certificate without editing certificate_id.",
    ),
    "stale_trace_after_certificate": BenchmarkLocalization(
        pcs_case_kind="stale_release",
        benchmark_failure_code="stale_trace_after_certificate",
        pcs_expected_status="failed",
        pcs_repair_hint_kind="align_certificate_id",
        pcs_responsible_component="runtime_producer",
        detection_layer="LabTrust",
        repair_command="labtrust regenerate-release-protocol --out examples/pcs_qc_release/release",
        operator_hint="Re-attach certificate after any trace change, or regenerate the protocol package.",
    ),
    "legacy_handoff_file": BenchmarkLocalization(
        pcs_case_kind="invalid_handoff",
        benchmark_failure_code="legacy_handoff_file",
        pcs_expected_status="failed",
        pcs_repair_hint_kind="align_handoff",
        pcs_responsible_component="handoff",
        detection_layer="LabTrust",
        repair_command=(
            "labtrust emit-handoff-to-pf --bundle examples/pcs_qc_release/release/"
            "science_claim_bundle.certified.json --out handoff_to_pf.json"
        ),
        operator_hint="Remove pf_handoff.json; emit handoff_to_pf.json (HandoffManifest.v0).",
    ),
    "placeholder_commit": BenchmarkLocalization(
        pcs_case_kind="invalid_registry",
        benchmark_failure_code="placeholder_source_commit",
        pcs_expected_status="failed",
        pcs_repair_hint_kind="align_provenance",
        pcs_responsible_component="runtime_producer",
        detection_layer="LabTrust",
        repair_command=(
            "PCS_DETERMINISTIC=1 labtrust regenerate-release-protocol "
            "--out examples/pcs_qc_release/release"
        ),
        operator_hint="Regenerate artifacts with real git provenance (no placeholder commits).",
    ),
    "lean_trace_hash_mismatch": BenchmarkLocalization(
        pcs_case_kind="invalid_formal_check",
        benchmark_failure_code="lean_certificate_trace_hash_mismatch",
        pcs_expected_status="failed",
        pcs_repair_hint_kind="rerun_formal_check",
        pcs_responsible_component="formal_kernel",
        detection_layer="Lean trust kernel",
        repair_command="labtrust regenerate-release-protocol --out examples/pcs_qc_release/release",
        operator_hint="Regenerate trace_certificate from the runtime receipt; align trace_hash fields.",
    ),
    "lean_rejected_certificate": BenchmarkLocalization(
        pcs_case_kind="invalid_formal_check",
        benchmark_failure_code="lean_certificate_rejected",
        pcs_expected_status="failed",
        pcs_repair_hint_kind="rerun_formal_check",
        pcs_responsible_component="formal_kernel",
        detection_layer="Lean trust kernel",
        repair_command="certifyedge emit-pcs-certificate ...",
        operator_hint="Re-emit certificate with CertificateChecked status after a passing runtime.",
    ),
    "lean_stale_certificate": BenchmarkLocalization(
        pcs_case_kind="invalid_formal_check",
        benchmark_failure_code="lean_certificate_stale",
        pcs_expected_status="failed",
        pcs_repair_hint_kind="rerun_formal_check",
        pcs_responsible_component="formal_kernel",
        detection_layer="Lean trust kernel",
        repair_command="labtrust attach-certificate ...",
        operator_hint="Re-attach certificate after trace mutation.",
    ),
    "lean_signed_hash_mismatch": BenchmarkLocalization(
        pcs_case_kind="invalid_formal_check",
        benchmark_failure_code="lean_verified_input_hash_mismatch",
        pcs_expected_status="failed",
        pcs_repair_hint_kind="rerun_verification",
        pcs_responsible_component="verifier",
        detection_layer="Provability Fabric",
        repair_command="pf verify-bundle ... && pf sign-bundle ...",
        operator_hint="Align verification_result.verified_input.bundle_hash with certified bundle digest.",
    ),
    "scientific_memory_import_failure": BenchmarkLocalization(
        pcs_case_kind="invalid_import",
        benchmark_failure_code="scientific_memory_claim_id_mismatch",
        pcs_expected_status="failed",
        pcs_repair_hint_kind="fix_import_report",
        pcs_responsible_component="scientific_memory",
        detection_layer="Scientific Memory",
        repair_command=(
            "pf sign-bundle ... && scientific-memory import-bundle "
            "signed_science_claim_bundle.json"
        ),
        operator_hint="Re-sign the bundle so signed claim_id matches the certified bundle.",
    ),
}


def valid_release_localization() -> BenchmarkLocalization:
    return BenchmarkLocalization(
        pcs_case_kind="valid_release",
        benchmark_failure_code="",
        pcs_expected_status="passed",
        pcs_repair_hint_kind="none",
        pcs_responsible_component="runtime_producer",
        detection_layer="LabTrust",
        repair_command=(
            "labtrust verify-release-protocol --release-dir examples/pcs_qc_release/release "
            "--pcs-core ../pcs-core"
        ),
        operator_hint="Release package passes LabTrust verify-release-protocol and status policy.",
    )


def localization_for(gallery_case_id: str) -> BenchmarkLocalization:
    loc = _LOCALIZATION_BY_GALLERY.get(gallery_case_id)
    if loc is None:
        raise ValueError(f"no benchmark localization for gallery case {gallery_case_id!r}")
    return loc


def build_benchmark_case_document(
    *,
    gallery_case_id: str,
    workflow_property_id: str,
    profile_workflow_id: str,
    expected_failing_check: str | None,
    expected_protocol_failure_code: str | None,
    artifact_names: list[str],
    policy_root: Path,
) -> dict[str, Any]:
    source_repo, source_commit = _benchmark_provenance(policy_root)
    if gallery_case_id == VALID_RELEASE_DIR_NAME:
        doc = build_valid_release_benchmark_case(
            workflow_property_id=workflow_property_id,
            profile_workflow_id=profile_workflow_id,
            artifact_names=artifact_names,
            policy_root=policy_root,
        )
        return doc

    loc = localization_for(gallery_case_id)
    doc: dict[str, Any] = {
        "schema_version": "v0",
        "case_id": benchmark_case_id_for(gallery_case_id),
        "task_id": BENCHMARK_TASK_ID,
        "workflow_id": workflow_property_id,
        "case_kind": loc.pcs_case_kind,
        "input_artifacts": {
            "release_directory": PCS_BENCH_RELEASE_DIRECTORY,
            "artifacts": _artifact_refs(artifact_names),
        },
        "expected_status": loc.pcs_expected_status,
        "expected_system_outcome": expected_system_outcome_for(loc.pcs_case_kind),
        "expected_failure_code": loc.benchmark_failure_code,
        "expected_responsible_component": loc.pcs_responsible_component,
        "expected_repair_hint_kind": loc.pcs_repair_hint_kind,
        "source_repo": source_repo,
        "source_commit": source_commit,
    }
    doc["signature_or_digest"] = _finalize_signature(doc)
    return doc


def build_valid_release_benchmark_case(
    *,
    workflow_property_id: str,
    profile_workflow_id: str,
    artifact_names: list[str],
    policy_root: Path,
) -> dict[str, Any]:
    source_repo, source_commit = _benchmark_provenance(policy_root)
    doc: dict[str, Any] = {
        "schema_version": "v0",
        "case_id": "labtrust-valid-release-v0",
        "task_id": BENCHMARK_TASK_ID,
        "workflow_id": workflow_property_id,
        "case_kind": "valid_release",
        "input_artifacts": {
            "release_directory": PCS_BENCH_RELEASE_DIRECTORY,
            "artifacts": _artifact_refs(artifact_names),
        },
        "expected_status": "passed",
        "expected_system_outcome": "admitted",
        "expected_failure_code": None,
        "expected_responsible_component": None,
        "expected_repair_hint_kind": None,
        "source_repo": source_repo,
        "source_commit": source_commit,
    }
    doc["signature_or_digest"] = _finalize_signature(doc)
    return doc


def build_labtrust_extension(
    *,
    gallery_case_id: str,
    profile_workflow_id: str,
    expected_failing_check: str | None,
    expected_protocol_failure_code: str | None,
    loc: BenchmarkLocalization,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": "v0",
        "gallery_case_id": gallery_case_id,
        "profile_workflow_id": profile_workflow_id,
        "expected_detection_layer": loc.detection_layer,
        "expected_failing_check": expected_failing_check,
        "expected_protocol_failure_code": expected_protocol_failure_code,
    }
    if gallery_case_id == VALID_RELEASE_DIR_NAME:
        doc["pcs_core_valid_case_compat"] = {
            "note": (
                "Valid benchmark_case.v0 uses null failure fields per pcs-core; "
                "repair hint remains for LabTrust operator guidance."
            ),
            "placeholder_fields": [],
        }
    return doc


def write_benchmark_case(case_dir: Path, doc: dict[str, Any]) -> Path:
    validate_benchmark_case(doc)
    path = case_dir / BENCHMARK_CASE_NAME
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_labtrust_extension(case_dir: Path, doc: dict[str, Any]) -> Path:
    path = case_dir / LABTRUST_EXTENSION_NAME
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_expected_failure(
    case_dir: Path,
    *,
    gallery_case_id: str,
    failing_check: str | None,
    benchmark_code: str,
    protocol_code: str | None,
) -> Path:
    path = case_dir / EXPECTED_FAILURE_NAME
    path.write_text(
        json.dumps(
            {
                "case_id": gallery_case_id,
                "expected_failing_check": failing_check,
                "expected_failure_code": benchmark_code,
                "expected_protocol_failure_code": protocol_code,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_expected_repair_hint(
    case_dir: Path,
    *,
    failure_code: str,
    responsible_component: str,
    detection_layer: str,
    hint_kind: str,
    command: str,
    hint: str,
) -> Path:
    path = case_dir / EXPECTED_REPAIR_HINT_NAME
    path.write_text(
        json.dumps(
            {
                "failure_code": failure_code,
                "responsible_component": responsible_component,
                "expected_detection_layer": detection_layer,
                "repair_hint": {
                    "kind": hint_kind,
                    "command": command,
                    "description": hint,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
