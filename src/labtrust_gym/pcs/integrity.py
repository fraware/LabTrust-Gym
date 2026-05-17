"""Cross-artifact integrity checks (LabTrust trace + pcs-core bundles)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.schema_version import SCHEMA_VERSION
from labtrust_gym.pcs.trace import compute_trace_hash, verify_event_hash_chain

REQUIRED_ROLES = (
    "accession_tech",
    "qc_tech",
    "analyst",
    "release_manager",
    "unauthorized_user",
)

REQUIRED_REASON_CODES = (
    "ok",
    "missing_qc",
    "unauthorized_release",
    "invalid_transition",
    "policy_denied",
)


def validate_trace_document(trace: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if trace.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"trace.schema_version must be {SCHEMA_VERSION!r}")
    for key in ("run_id", "sample_id", "events", "trace_hash"):
        if key not in trace:
            errors.append(f"trace missing {key!r}")
    events = trace.get("events", [])
    if not isinstance(events, list):
        errors.append("trace.events must be a list")
        return errors
    errors.extend(verify_event_hash_chain(events))
    if "run_id" in trace and "sample_id" in trace:
        expected = compute_trace_hash(events, run_id=str(trace["run_id"]), sample_id=str(trace["sample_id"]))
        if trace.get("trace_hash") != expected:
            errors.append("trace.trace_hash does not match canonical computation")
    return errors


def validate_receipt_against_trace(receipt: dict[str, Any], trace: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if receipt.get("trace_hash") != trace.get("trace_hash"):
        errors.append(
            "runtime_receipt.trace_hash != trace.trace_hash "
            f"({receipt.get('trace_hash')!r} vs {trace.get('trace_hash')!r})"
        )
    trace_path_hash = receipt.get("output_hashes", {}).get("trace.json")
    if not trace_path_hash:
        errors.append("runtime_receipt.output_hashes missing trace.json")
    return errors


def validate_bundle_internal_refs(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    claim = bundle.get("claim_artifact", {})
    assumption = bundle.get("assumption_set", {})
    if claim.get("assumption_set_ref") != assumption.get("assumption_set_id"):
        errors.append("claim_artifact.assumption_set_ref != assumption_set.assumption_set_id")
    receipts = bundle.get("runtime_receipts") or []
    if not receipts:
        errors.append("ScienceClaimBundle requires runtime_receipts")
        return errors
    receipt = receipts[0]
    claim_refs = set(claim.get("runtime_receipt_refs") or [])
    if receipt.get("receipt_id") not in claim_refs:
        errors.append("claim_artifact.runtime_receipt_refs missing receipt_id")
    evidence = bundle.get("evidence_bundle", {})
    if receipt.get("receipt_id") not in (evidence.get("runtime_receipt_refs") or []):
        errors.append("evidence_bundle.runtime_receipt_refs missing receipt_id")
    for cert in bundle.get("certificates") or []:
        if cert.get("trace_hash") != receipt.get("trace_hash"):
            errors.append(f"certificate {cert.get('certificate_id')}: trace_hash != receipt.trace_hash")
    return errors


def validate_run_directory(run_dir: Path) -> list[str]:
    """Validate trace + optional exported PCS artifacts under a run directory."""
    errors: list[str] = []
    trace_path = run_dir / "trace.json"
    if not trace_path.is_file():
        return [f"{trace_path}: missing trace.json"]
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    errors.extend(f"trace: {e}" for e in validate_trace_document(trace))

    meta_path = run_dir / "run_meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("trace_hash") and meta["trace_hash"] != trace.get("trace_hash"):
            errors.append("run_meta.trace_hash != trace.trace_hash")

    receipt_path = run_dir / "pcs" / "runtime_receipt.json"
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        errors.extend(f"runtime_receipt: {e}" for e in validate_receipt_against_trace(receipt, trace))

    for name in ("science_claim_bundle.pending.json", "science_claim_bundle.certified.json"):
        bundle_path = run_dir / "pcs" / name
        if bundle_path.is_file():
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            errors.extend(f"bundle: {e}" for e in validate_bundle_internal_refs(bundle))
            errors.extend(f"bundle: {e}" for e in validate_receipt_against_trace(bundle["runtime_receipts"][0], trace))
    return errors
