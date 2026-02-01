"""
FHIR R4 export: convert Receipt.v0.1 (from evidence bundle) into a minimal FHIR R4 Bundle.

- Bundle type = "collection" with Specimen, Observation(s), DiagnosticReport.
- No external FHIR libs; pure JSON dicts with lightweight structural validation.
- Deterministic: same receipts => identical bundle JSON (canonical ordering).
- Partner overlay: partner_id in Bundle.meta.tag, policy_fingerprint in meta.extension.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FHIR_BUNDLE_TYPE = "collection"
FHIR_VERSION = "4.0.1"


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True)


def _timestamp_to_fhir_datetime(t_s: Optional[int]) -> Optional[str]:
    """Convert sim timestamp (seconds) to FHIR dateTime (UTC ISO 8601). Epoch 0 = 1970-01-01."""
    if t_s is None:
        return None
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(int(t_s), tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_receipts_from_dir(receipts_dir: Path) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
    """
    Load all receipt_*.v0.1.json from directory; read partner_id and policy_fingerprint from manifest if present.
    Returns (receipts, partner_id, policy_fingerprint). Receipts sorted by entity_type then specimen_id/result_id.
    """
    receipts_dir = Path(receipts_dir)
    partner_id: Optional[str] = None
    policy_fingerprint: Optional[str] = None
    manifest_path = receipts_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            partner_id = manifest.get("partner_id")
            policy_fingerprint = manifest.get("policy_fingerprint")
        except Exception:
            pass
    receipts: List[Dict[str, Any]] = []
    for p in sorted(receipts_dir.glob("receipt_*.v0.1.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("version") == "0.1":
                receipts.append(data)
        except Exception:
            continue
    # Deterministic order: specimen first (by specimen_id), then result (by result_id)
    def _sort_key(r: Dict[str, Any]) -> tuple:
        et = r.get("entity_type", "")
        sid = r.get("specimen_id") or ""
        rid = r.get("result_id") or ""
        return (0 if et == "specimen" else 1, sid, rid)
    receipts.sort(key=_sort_key)
    return receipts, partner_id, policy_fingerprint


def _receipt_to_fhir_specimen(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Map receipt (entity_type=specimen) to FHIR R4 Specimen."""
    sid = receipt.get("specimen_id") or "unknown"
    accession_ids = receipt.get("accession_ids") or []
    accession_id = accession_ids[0] if accession_ids else None
    timestamps = receipt.get("timestamps") or {}
    received_ts = timestamps.get("received") or timestamps.get("accepted")
    received_time = _timestamp_to_fhir_datetime(received_ts) if received_ts is not None else None
    spec: Dict[str, Any] = {
        "resourceType": "Specimen",
        "id": sid,
        "identifier": [{"system": "urn:labtrust:specimen", "value": sid}],
    }
    if accession_id:
        spec["accessionIdentifier"] = {"value": accession_id}
    if received_time:
        spec["receivedTime"] = received_time
    if received_ts is not None and received_time is None:
        spec.setdefault("extension", []).append({
            "url": "http://labtrust.org/fhir/StructureDefinition/received-timestamp",
            "valueInteger": int(received_ts),
        })
    return spec


def _receipt_to_fhir_observation(
    receipt: Dict[str, Any],
    index: int,
    interpretation_from_reason: bool = True,
) -> Dict[str, Any]:
    """Map receipt (entity_type=result) to FHIR R4 Observation."""
    rid = receipt.get("result_id") or f"obs-{index}"
    panel_id = receipt.get("panel_id") or rid
    device_ids = receipt.get("device_ids") or []
    device_id = device_ids[0] if device_ids else None
    reason_codes = receipt.get("reason_codes") or []
    timestamps = receipt.get("timestamps") or {}
    issued_ts = timestamps.get("result_generated") or timestamps.get("released")
    issued = _timestamp_to_fhir_datetime(issued_ts) if issued_ts is not None else None
    obs: Dict[str, Any] = {
        "resourceType": "Observation",
        "id": rid,
        "status": "final",
        "code": {
            "coding": [{"system": "urn:labtrust:test", "code": panel_id, "display": panel_id}],
        },
    }
    # Value: receipt has no numeric value; use placeholder or valueString
    obs["valueString"] = "result"
    if interpretation_from_reason:
        interp: List[Dict[str, Any]] = []
        for rc in reason_codes:
            rc_upper = (rc or "").upper()
            if "CRIT" in rc_upper or "CRITICAL" in rc_upper:
                interp.append({"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "code": "CR", "display": "Critical"}]})
                break
            if "HIGH" in rc_upper:
                interp.append({"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "code": "H", "display": "High"}]})
                break
            if "LOW" in rc_upper:
                interp.append({"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "code": "L", "display": "Low"}]})
                break
        if interp:
            obs["interpretation"] = interp
    if device_id:
        obs.setdefault("extension", []).append({
            "url": "http://labtrust.org/fhir/StructureDefinition/device-identifier",
            "valueIdentifier": {"system": "urn:labtrust:device", "value": device_id},
        })
    if issued:
        obs["issued"] = issued
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
    receipt: Dict[str, Any],
    specimen_ref: str,
    observation_refs: List[str],
) -> Dict[str, Any]:
    """Map receipt (entity_type=result) to FHIR R4 DiagnosticReport."""
    rid = receipt.get("result_id") or "dr-unknown"
    status = _diagnostic_report_status(receipt.get("decision", ""))
    timestamps = receipt.get("timestamps") or {}
    issued_ts = timestamps.get("result_generated") or timestamps.get("released")
    issued = _timestamp_to_fhir_datetime(issued_ts) if issued_ts is not None else None
    dr: Dict[str, Any] = {
        "resourceType": "DiagnosticReport",
        "id": rid,
        "status": status,
        "specimen": [{"reference": specimen_ref}],
        "result": [{"reference": ref} for ref in observation_refs],
    }
    if issued:
        dr["effectiveDateTime"] = issued
    return dr


def receipts_to_fhir_bundle(
    receipts: List[Dict[str, Any]],
    partner_id: Optional[str] = None,
    policy_fingerprint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build FHIR R4 Bundle (type=collection) from receipts.
    Deterministic: specimens first, then observations (one per result receipt), then diagnostic reports.
    Each result receipt produces one Observation and one DiagnosticReport; specimen ref = first Specimen in bundle.
    """
    specimens: List[Dict[str, Any]] = []
    result_receipts: List[Dict[str, Any]] = []
    for r in receipts:
        if r.get("entity_type") == "specimen":
            specimens.append(r)
        elif r.get("entity_type") == "result":
            result_receipts.append(r)
    # Build resources
    fhir_specimens: List[Dict[str, Any]] = [_receipt_to_fhir_specimen(s) for s in specimens]
    first_specimen_id = fhir_specimens[0]["id"] if fhir_specimens else None
    specimen_ref = f"#Specimen/{first_specimen_id}" if first_specimen_id else None
    if not specimen_ref and result_receipts:
        specimen_ref = "#Specimen/placeholder"
        fhir_specimens.append({"resourceType": "Specimen", "id": "placeholder", "identifier": [{"system": "urn:labtrust:specimen", "value": "placeholder"}]})
    fhir_observations: List[Dict[str, Any]] = [_receipt_to_fhir_observation(r, i) for i, r in enumerate(result_receipts)]
    fhir_reports: List[Dict[str, Any]] = []
    for i, r in enumerate(result_receipts):
        obs_id = fhir_observations[i]["id"] if i < len(fhir_observations) else f"obs-{i}"
        obs_refs = [f"#Observation/{obs_id}"]
        fhir_reports.append(_receipt_to_fhir_diagnostic_report(r, specimen_ref or "#Specimen/unknown", obs_refs))
    # Bundle.entry: deterministic order Specimen(s), Observation(s), DiagnosticReport(s)
    entries: List[Dict[str, Any]] = []
    for s in fhir_specimens:
        entries.append({"fullUrl": f"#Specimen/{s['id']}", "resource": s})
    for o in fhir_observations:
        entries.append({"fullUrl": f"#Observation/{o['id']}", "resource": o})
    for d in fhir_reports:
        entries.append({"fullUrl": f"#DiagnosticReport/{d['id']}", "resource": d})
    bundle: Dict[str, Any] = {
        "resourceType": "Bundle",
        "meta": {},
        "type": FHIR_BUNDLE_TYPE,
        "entry": entries,
    }
    if partner_id:
        bundle["meta"]["tag"] = [{"system": "http://labtrust.org/fhir/partner", "code": partner_id}]
    if policy_fingerprint:
        bundle["meta"].setdefault("extension", []).append({
            "url": "http://labtrust.org/fhir/StructureDefinition/policy-fingerprint",
            "valueString": policy_fingerprint,
        })
    return bundle


def validate_bundle_structure(bundle: Dict[str, Any]) -> List[str]:
    """
    Lightweight structural validation: required keys, references resolve within bundle.
    Returns list of error messages (empty if valid).
    """
    errors: List[str] = []
    if bundle.get("resourceType") != "Bundle":
        errors.append("Bundle must have resourceType 'Bundle'")
    if bundle.get("type") != FHIR_BUNDLE_TYPE:
        errors.append(f"Bundle.type must be '{FHIR_BUNDLE_TYPE}'")
    entries = bundle.get("entry")
    if not isinstance(entries, list):
        errors.append("Bundle.entry must be an array")
        return errors
    ids: set = set()
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
        if full_url and full_url.startswith("#"):
            ids.add(full_url)
        elif rid:
            ids.add(f"#{rt}/{rid}")
    for i, e in enumerate(entries):
        resource = e.get("resource") or {}
        for ref_key in ("specimen", "result"):
            refs = resource.get(ref_key)
            if isinstance(refs, list):
                for ref_obj in refs:
                    ref = ref_obj.get("reference") if isinstance(ref_obj, dict) else None
                    if ref and ref.startswith("#") and ref not in ids:
                        errors.append(f"entry[{i}].resource.{ref_key} reference '{ref}' not found in bundle")
            elif isinstance(refs, dict) and refs.get("reference") and refs["reference"].startswith("#"):
                if refs["reference"] not in ids:
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
