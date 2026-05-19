"""BenchmarkCase.v0 builders and localization metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.bench_schemas import validate_benchmark_case

BENCHMARK_CASE_NAME = "benchmark_case.v0.json"
BENCHMARK_TASK_ID = "labtrust-qc-release-failure-localization-v0"
VALID_RELEASE_DIR_NAME = "valid_release"
INPUT_ARTIFACTS_DIR = "input_artifacts"
EXPECTED_FAILURE_NAME = "expected_failure.json"
EXPECTED_REPAIR_HINT_NAME = "expected_repair_hint.json"

DETECTION_LAYERS = (
    "LabTrust",
    "CertifyEdge",
    "Provability Fabric",
    "pcs-core",
    "Lean trust kernel",
    "Scientific Memory",
)


@dataclass(frozen=True)
class BenchmarkLocalization:
    case_kind: str
    benchmark_failure_code: str
    expected_status: str
    repair_hint_kind: str
    detection_layer: str
    repair_command: str


def benchmark_case_id_for(gallery_case_id: str) -> str:
    slug = gallery_case_id.replace("_", "-")
    return f"labtrust-{slug}-v0"


def detection_layer_for(responsible_component: str) -> str:
    mapping = {
        "workflow.runtime": "LabTrust",
        "workflow.handoff": "LabTrust",
        "workflow.status_policy": "LabTrust",
        "workflow.provenance": "LabTrust",
        "runtime_producer": "LabTrust",
        "certifyedge.certificate": "CertifyEdge",
        "provability_fabric.verifier": "Provability Fabric",
        "pcs_core.validator": "pcs-core",
        "lean.extraction": "Lean trust kernel",
        "scientific_memory.importer": "Scientific Memory",
    }
    return mapping.get(responsible_component, "LabTrust")


def responsible_component_alias(component: str) -> str:
    aliases = {
        "workflow.runtime": "runtime_producer",
        "workflow.handoff": "runtime_producer",
        "workflow.status_policy": "runtime_producer",
        "workflow.provenance": "runtime_producer",
    }
    return aliases.get(component, component)


_LOCALIZATION_BY_GALLERY: dict[str, BenchmarkLocalization] = {
    "missing_qc_result": BenchmarkLocalization(
        case_kind="missing_qc_step",
        benchmark_failure_code="missing_qc",
        expected_status="Rejected",
        repair_hint_kind="complete_qc_before_release",
        detection_layer="LabTrust",
        repair_command=(
            "labtrust run-demo qc-release --deterministic --out <run_dir> "
            "&& labtrust export-runtime-receipt --run <run_dir> --out runtime_receipt.json"
        ),
    ),
    "unauthorized_release": BenchmarkLocalization(
        case_kind="unauthorized_actor",
        benchmark_failure_code="unauthorized_release",
        expected_status="Rejected",
        repair_hint_kind="use_authorized_release_actor",
        detection_layer="LabTrust",
        repair_command="labtrust run-demo qc-release --deterministic --out <run_dir>",
    ),
    "trace_hash_tamper": BenchmarkLocalization(
        case_kind="invalid_hash_mismatch",
        benchmark_failure_code="trace_hash_mismatch",
        expected_status="Rejected",
        repair_hint_kind="regenerate_trace_or_certificate",
        detection_layer="LabTrust",
        repair_command=(
            "labtrust regenerate-release-protocol --out examples/pcs_qc_release/release "
            "--certifyedge-bin certifyedge --pcs-core ../pcs-core"
        ),
    ),
    "certificate_id_tamper": BenchmarkLocalization(
        case_kind="certificate_tamper",
        benchmark_failure_code="certificate_id_mismatch",
        expected_status="Rejected",
        repair_hint_kind="re_emit_certificate",
        detection_layer="CertifyEdge",
        repair_command=(
            "certifyedge emit-pcs-certificate ... && labtrust attach-certificate "
            "--bundle science_claim_bundle.pending.json --certificate trace_certificate.json"
        ),
    ),
    "stale_trace_after_certificate": BenchmarkLocalization(
        case_kind="status_transition",
        benchmark_failure_code="stale_trace_after_certificate",
        expected_status="Stale",
        repair_hint_kind="reattach_certificate_after_trace_change",
        detection_layer="LabTrust",
        repair_command="labtrust regenerate-release-protocol --out <release-dir>",
    ),
    "legacy_handoff_file": BenchmarkLocalization(
        case_kind="handoff_tamper",
        benchmark_failure_code="legacy_handoff_file",
        expected_status="Rejected",
        repair_hint_kind="emit_handoff_manifest_v0",
        detection_layer="LabTrust",
        repair_command="labtrust emit-handoff-to-pf --bundle <certified.json> --out handoff_to_pf.json",
    ),
    "placeholder_commit": BenchmarkLocalization(
        case_kind="provenance_invalid",
        benchmark_failure_code="placeholder_source_commit",
        expected_status="Rejected",
        repair_hint_kind="regenerate_with_real_provenance",
        detection_layer="LabTrust",
        repair_command="PCS_DETERMINISTIC=1 labtrust regenerate-release-protocol --out <release-dir>",
    ),
    "lean_trace_hash_mismatch": BenchmarkLocalization(
        case_kind="formal_check_failure",
        benchmark_failure_code="lean_certificate_trace_hash_mismatch",
        expected_status="Rejected",
        repair_hint_kind="align_certificate_trace_hash",
        detection_layer="Lean trust kernel",
        repair_command="labtrust regenerate-release-protocol --out <release-dir>",
    ),
    "lean_rejected_certificate": BenchmarkLocalization(
        case_kind="formal_check_failure",
        benchmark_failure_code="lean_certificate_rejected",
        expected_status="Rejected",
        repair_hint_kind="re_emit_valid_certificate",
        detection_layer="Lean trust kernel",
        repair_command="certifyedge emit-pcs-certificate ...",
    ),
    "lean_stale_certificate": BenchmarkLocalization(
        case_kind="formal_check_failure",
        benchmark_failure_code="lean_certificate_stale",
        expected_status="Stale",
        repair_hint_kind="reattach_certificate_after_trace_change",
        detection_layer="Lean trust kernel",
        repair_command="labtrust attach-certificate ...",
    ),
    "lean_signed_hash_mismatch": BenchmarkLocalization(
        case_kind="formal_check_failure",
        benchmark_failure_code="lean_verified_input_hash_mismatch",
        expected_status="Rejected",
        repair_hint_kind="align_verification_and_bundle_hash",
        detection_layer="Provability Fabric",
        repair_command="pf verify-bundle ... && pf sign-bundle ...",
    ),
}


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
    expected_failing_check: str,
    expected_protocol_failure_code: str,
    responsible_component: str,
    repair_hint: str,
) -> dict[str, Any]:
    loc = localization_for(gallery_case_id)
    return {
        "schema_version": "v0",
        "case_id": benchmark_case_id_for(gallery_case_id),
        "task_id": BENCHMARK_TASK_ID,
        "workflow_id": workflow_property_id,
        "profile_workflow_id": profile_workflow_id,
        "gallery_case_id": gallery_case_id,
        "case_kind": loc.case_kind,
        "expected_status": loc.expected_status,
        "expected_failure_code": loc.benchmark_failure_code,
        "expected_protocol_failure_code": expected_protocol_failure_code,
        "expected_responsible_component": responsible_component_alias(responsible_component),
        "expected_repair_hint_kind": loc.repair_hint_kind,
        "expected_detection_layer": loc.detection_layer,
        "expected_failing_check": expected_failing_check,
        "expected_repair_command": loc.repair_command,
    }


def build_valid_release_benchmark_case(
    *,
    workflow_property_id: str,
    profile_workflow_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": "v0",
        "case_id": "labtrust-valid-release-v0",
        "task_id": BENCHMARK_TASK_ID,
        "workflow_id": workflow_property_id,
        "profile_workflow_id": profile_workflow_id,
        "gallery_case_id": VALID_RELEASE_DIR_NAME,
        "case_kind": "valid_release",
        "expected_status": "CertificateChecked",
        "expected_failure_code": None,
        "expected_protocol_failure_code": None,
        "expected_responsible_component": "runtime_producer",
        "expected_repair_hint_kind": "none",
        "expected_detection_layer": "LabTrust",
        "expected_failing_check": None,
        "expected_repair_command": (
            "labtrust verify-release-protocol --release-dir examples/pcs_qc_release/release "
            "--pcs-core ../pcs-core"
        ),
    }


def write_benchmark_case(case_dir: Path, doc: dict[str, Any]) -> Path:
    validate_benchmark_case(doc)
    path = case_dir / BENCHMARK_CASE_NAME
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_expected_failure(case_dir: Path, *, gallery_case_id: str, failing_check: str, code: str) -> Path:
    path = case_dir / EXPECTED_FAILURE_NAME
    path.write_text(
        json.dumps(
            {
                "case_id": gallery_case_id,
                "expected_failing_check": failing_check,
                "expected_failure_code": code,
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
    hint_kind: str,
    hint: str,
    repair_command: str,
) -> Path:
    path = case_dir / EXPECTED_REPAIR_HINT_NAME
    path.write_text(
        json.dumps(
            {
                "hint_kind": hint_kind,
                "hint": hint,
                "repair_command": repair_command,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
