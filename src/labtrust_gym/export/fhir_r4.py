"""
FHIR R4 export: convert Receipt.v0.1 (from evidence bundle) into a minimal FHIR R4 Bundle.

- Bundle type = "collection" with Specimen, Observation(s), DiagnosticReport.
- No external FHIR libs; pure JSON dicts with lightweight structural validation.
- Deterministic: same receipts => identical bundle JSON (canonical ordering).
- Partner overlay: partner_id in Bundle.meta.tag, policy_fingerprint in meta.extension.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC
from pathlib import Path
from typing import Any

FHIR_BUNDLE_TYPE = "collection"
FHIR_VERSION = "4.0.1"

# HL7 data-absent-reason: when specimen or value is missing (no placeholder IDs)
DATA_ABSENT_REASON_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/data-absent-reason"
DATA_ABSENT_REASON_CODESYSTEM = "http://terminology.hl7.org/CodeSystem/data-absent-reason"
DATA_ABSENT_REASON_CODE_UNKNOWN = "unknown"


def _specimen_reference_data_absent() -> dict[str, Any]:
    """Reference object with only data-absent-reason extension (no reference, no Specimen resource)."""
    return {
        "extension": [
            {
                "url": DATA_ABSENT_REASON_EXTENSION_URL,
                "valueCode": DATA_ABSENT_REASON_CODE_UNKNOWN,
            }
        ]
    }


def _observation_data_absent_reason() -> dict[str, Any]:
    """Observation.dataAbsentReason when no numeric value (omit value[x])."""
    return {
        "coding": [
            {
                "system": DATA_ABSENT_REASON_CODESYSTEM,
                "code": DATA_ABSENT_REASON_CODE_UNKNOWN,
            }
        ]
    }


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True)


def _timestamp_to_fhir_datetime(t_s: int | None) -> str | None:
    """Convert sim timestamp (seconds) to FHIR dateTime (UTC ISO 8601). Epoch 0 = 1970-01-01."""
    if t_s is None:
        return None
    from datetime import datetime

    dt = datetime.fromtimestamp(int(t_s), tz=UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_receipts_from_dir(
    receipts_dir: Path,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """
    Load all receipt_*.v0.1.json from directory; read partner_id and policy_fingerprint from manifest if present.
    Returns (receipts, partner_id, policy_fingerprint). Receipts sorted by entity_type then specimen_id/result_id.
    """
    receipts_dir = Path(receipts_dir)
    partner_id: str | None = None
    policy_fingerprint: str | None = None
    manifest_path = receipts_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            partner_id = manifest.get("partner_id")
            policy_fingerprint = manifest.get("policy_fingerprint")
        except Exception:
            pass
    receipts: list[dict[str, Any]] = []
    for p in sorted(receipts_dir.glob("receipt_*.v0.1.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("version") == "0.1":
                receipts.append(data)
        except Exception:
            continue

    # Deterministic order: specimen first (by specimen_id), then result (by result_id)
    def _sort_key(r: dict[str, Any]) -> tuple[int, str, str]:
        et = r.get("entity_type", "")
        sid = r.get("specimen_id") or ""
        rid = r.get("result_id") or ""
        return (0 if et == "specimen" else 1, sid, rid)

    receipts.sort(key=_sort_key)
    return receipts, partner_id, policy_fingerprint


def _specimen_id_from_receipt(receipt: dict[str, Any]) -> str:
    """Deterministic id when specimen_id is missing: content-addressed hash of receipt."""
    canonical = json.dumps(receipt, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _receipt_to_fhir_specimen(receipt: dict[str, Any]) -> dict[str, Any]:
    """Map receipt (entity_type=specimen) to FHIR R4 Specimen. Id = specimen_id or content-addressed hash."""
    raw_sid = (receipt.get("specimen_id") or "").strip()
    sid = raw_sid if raw_sid else _specimen_id_from_receipt(receipt)
    accession_ids = receipt.get("accession_ids") or []
    accession_id = accession_ids[0] if accession_ids else None
    timestamps = receipt.get("timestamps") or {}
    received_ts = timestamps.get("received") or timestamps.get("accepted")
    received_time = _timestamp_to_fhir_datetime(received_ts) if received_ts is not None else None
    spec: dict[str, Any] = {
        "resourceType": "Specimen",
        "id": sid,
        "identifier": [{"system": "urn:labtrust:specimen", "value": sid}],
    }
    if accession_id:
        spec["accessionIdentifier"] = {"value": accession_id}
    if received_time:
        spec["receivedTime"] = received_time
    if received_ts is not None and received_time is None:
        spec.setdefault("extension", []).append(
            {
                "url": "http://labtrust.org/fhir/StructureDefinition/received-timestamp",
                "valueInteger": int(received_ts),
            }
        )
    return spec


def _receipt_to_fhir_observation(
    receipt: dict[str, Any],
    index: int,
    specimen_ref_or_extension: str | dict[str, Any],
    interpretation_from_reason: bool = True,
) -> dict[str, Any]:
    """Map receipt (entity_type=result) to FHIR R4 Observation. Specimen is reference or data-absent extension."""
    rid = receipt.get("result_id") or f"obs-{index}"
    panel_id = receipt.get("panel_id") or rid
    device_ids = receipt.get("device_ids") or []
    device_id = device_ids[0] if device_ids else None
    reason_codes = receipt.get("reason_codes") or []
    timestamps = receipt.get("timestamps") or {}
    issued_ts = timestamps.get("result_generated") or timestamps.get("released")
    issued = _timestamp_to_fhir_datetime(issued_ts) if issued_ts is not None else None
    obs: dict[str, Any] = {
        "resourceType": "Observation",
        "id": rid,
        "status": "final",
        "code": {
            "coding": [{"system": "urn:labtrust:test", "code": panel_id, "display": panel_id}],
        },
    }
    # No numeric value in receipt: omit value[x], use dataAbsentReason per R4
    obs["dataAbsentReason"] = _observation_data_absent_reason()
    if interpretation_from_reason:
        interp: list[dict[str, Any]] = []
        for rc in reason_codes:
            rc_upper = (rc or "").upper()
            if "CRIT" in rc_upper or "CRITICAL" in rc_upper:
                interp.append(
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                                "code": "CR",
                                "display": "Critical",
                            }
                        ]
                    }
                )
                break
            if "HIGH" in rc_upper:
                interp.append(
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                                "code": "H",
                                "display": "High",
                            }
                        ]
                    }
                )
                break
            if "LOW" in rc_upper:
                interp.append(
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                                "code": "L",
                                "display": "Low",
                            }
                        ]
                    }
                )
                break
        if interp:
            obs["interpretation"] = interp
    if device_id:
        obs.setdefault("extension", []).append(
            {
                "url": "http://labtrust.org/fhir/StructureDefinition/device-identifier",
                "valueIdentifier": {"system": "urn:labtrust:device", "value": device_id},
            }
        )
    if issued:
        obs["issued"] = issued
    # Specimen: reference when present, or Reference with data-absent-reason extension when missing
    if isinstance(specimen_ref_or_extension, str):
        obs["specimen"] = {"reference": specimen_ref_or_extension}
    else:
        obs["specimen"] = specimen_ref_or_extension
    return obs


def _diagnostic_report_status(decision: str) -> str:
    """Map receipt decision to DiagnosticReport.status."""
    d = (decision or "").upper()
    if d == "RELEASED":
        return "final"
    if d == "HELD":
        return "partial"
    if d == "REJECTED":
        return "entered-in-error"
    return "registered"


def _receipt_to_fhir_diagnostic_report(
    receipt: dict[str, Any],
    specimen_ref_or_extension: str | dict[str, Any],
    observation_refs: list[str],
) -> dict[str, Any]:
    """Map receipt (entity_type=result) to FHIR R4 DiagnosticReport. Specimen is reference or data-absent extension."""
    rid = receipt.get("result_id") or "dr-unknown"
    status = _diagnostic_report_status(receipt.get("decision", ""))
    timestamps = receipt.get("timestamps") or {}
    issued_ts = timestamps.get("result_generated") or timestamps.get("released")
    issued = _timestamp_to_fhir_datetime(issued_ts) if issued_ts is not None else None
    dr: dict[str, Any] = {
        "resourceType": "DiagnosticReport",
        "id": rid,
        "status": status,
        "result": [{"reference": ref} for ref in observation_refs],
    }
    if isinstance(specimen_ref_or_extension, str):
        dr["specimen"] = [{"reference": specimen_ref_or_extension}]
    else:
        dr["specimen"] = [specimen_ref_or_extension]
    if issued:
        dr["effectiveDateTime"] = issued
    return dr


def receipts_to_fhir_bundle(
    receipts: list[dict[str, Any]],
    partner_id: str | None = None,
    policy_fingerprint: str | None = None,
) -> dict[str, Any]:
    """
    Build FHIR R4 Bundle (type=collection) from receipts.
    Deterministic: specimens first, then observations (one per result receipt), then diagnostic reports.
    When specimen receipts exist: Specimen resources with deterministic ids; Observation/DiagnosticReport
    reference them. When none exist: no Specimen; Observation.specimen and DiagnosticReport.specimen
    use data-absent-reason extension only. No placeholder IDs anywhere.
    """
    specimens: list[dict[str, Any]] = []
    result_receipts: list[dict[str, Any]] = []
    for r in receipts:
        if r.get("entity_type") == "specimen":
            specimens.append(r)
        elif r.get("entity_type") == "result":
            result_receipts.append(r)
    fhir_specimens: list[dict[str, Any]] = [_receipt_to_fhir_specimen(s) for s in specimens]
    first_specimen_id = fhir_specimens[0]["id"] if fhir_specimens else None
    if first_specimen_id:
        specimen_ref_or_extension: str | dict[str, Any] = f"#Specimen/{first_specimen_id}"
    else:
        specimen_ref_or_extension = _specimen_reference_data_absent()
    fhir_observations: list[dict[str, Any]] = [
        _receipt_to_fhir_observation(r, i, specimen_ref_or_extension)
        for i, r in enumerate(result_receipts)
    ]
    fhir_reports: list[dict[str, Any]] = []
    for i, r in enumerate(result_receipts):
        obs_id = fhir_observations[i]["id"] if i < len(fhir_observations) else f"obs-{i}"
        obs_refs = [f"#Observation/{obs_id}"]
        fhir_reports.append(_receipt_to_fhir_diagnostic_report(r, specimen_ref_or_extension, obs_refs))
    # Bundle.entry: deterministic order Specimen(s), Observation(s), DiagnosticReport(s)
    entries: list[dict[str, Any]] = []
    for s in fhir_specimens:
        entries.append({"fullUrl": f"#Specimen/{s['id']}", "resource": s})
    for o in fhir_observations:
        entries.append({"fullUrl": f"#Observation/{o['id']}", "resource": o})
    for d in fhir_reports:
        entries.append({"fullUrl": f"#DiagnosticReport/{d['id']}", "resource": d})
    bundle: dict[str, Any] = {
        "resourceType": "Bundle",
        "meta": {},
        "type": FHIR_BUNDLE_TYPE,
        "entry": entries,
    }
    if partner_id:
        bundle["meta"]["tag"] = [{"system": "http://labtrust.org/fhir/partner", "code": partner_id}]
    if policy_fingerprint:
        bundle["meta"].setdefault("extension", []).append(
            {
                "url": "http://labtrust.org/fhir/StructureDefinition/policy-fingerprint",
                "valueString": policy_fingerprint,
            }
        )
    return bundle


def validate_bundle_structure(bundle: dict[str, Any]) -> list[str]:
    """
    Lightweight structural validation: required keys, references resolve within bundle.
    No placeholder IDs. Observation/DiagnosticReport.specimen may be extension-only (data-absent-reason).
    Returns list of error messages (empty if valid).
    """
    errors: list[str] = []
    if bundle.get("resourceType") != "Bundle":
        errors.append("Bundle must have resourceType 'Bundle'")
    if bundle.get("type") != FHIR_BUNDLE_TYPE:
        errors.append(f"Bundle.type must be '{FHIR_BUNDLE_TYPE}'")
    entries = bundle.get("entry")
    if not isinstance(entries, list):
        errors.append("Bundle.entry must be an array")
        return errors
    ids: set[str] = set()
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            errors.append(f"entry[{i}] must be an object")
            continue
        full_url = e.get("fullUrl", "")
        resource = e.get("resource")
        if not isinstance(resource, dict):
            errors.append(f"entry[{i}].resource missing or not object")
            continue
        rt = resource.get("resourceType")
        rid = resource.get("id")
        if rid == "placeholder" or (isinstance(rid, str) and "placeholder" in rid.lower()):
            errors.append(f"entry[{i}].resource.id must not be placeholder")
        if full_url and full_url.startswith("#"):
            ids.add(full_url)
            if "placeholder" in full_url.lower():
                errors.append(f"entry[{i}].fullUrl must not contain placeholder")
        elif rid:
            ids.add(f"#{rt}/{rid}")
    for i, e in enumerate(entries):
        resource = e.get("resource") or {}
        for ref_key in ("specimen", "result"):
            refs = resource.get(ref_key)
            if isinstance(refs, list):
                for ref_obj in refs:
                    if not isinstance(ref_obj, dict):
                        continue
                    ref = ref_obj.get("reference")
                    if ref and ref.startswith("#") and ref not in ids:
                        errors.append(f"entry[{i}].resource.{ref_key} reference '{ref}' not found in bundle")
            elif isinstance(refs, dict):
                ref = refs.get("reference")
                if ref and ref.startswith("#") and ref not in ids:
                    errors.append(f"entry[{i}].resource.{ref_key} reference not found in bundle")
    return errors


def export_fhir(
    receipts_dir: Path,
    out_dir: Path,
    out_filename: str = "fhir_bundle.json",
) -> Path:
    """
    Load receipts from receipts_dir (EvidenceBundle.v0.1 or dir of receipt_*.v0.1.json),
    build FHIR Bundle, validate structure, write to out_dir/out_filename.
    Returns path to written file.
    """
    receipts_dir = Path(receipts_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    receipts, partner_id, policy_fingerprint = load_receipts_from_dir(receipts_dir)
    bundle = receipts_to_fhir_bundle(receipts, partner_id=partner_id, policy_fingerprint=policy_fingerprint)
    errs = validate_bundle_structure(bundle)
    if errs:
        raise ValueError("FHIR bundle validation failed: " + "; ".join(errs))
    out_path = out_dir / out_filename
    out_path.write_text(_canonical_json(bundle) + "\n", encoding="utf-8")
    return out_path
