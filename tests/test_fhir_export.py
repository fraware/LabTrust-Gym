"""
FHIR R4 export: one receipt -> bundle refs, multiple observations per report, critical interpretation.

- Determinism: same receipts => identical bundle JSON.
- Structural validation and export contract schema.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.export.fhir_r4 import (
    export_fhir,
    receipts_to_fhir_bundle,
    validate_bundle_structure,
)
from labtrust_gym.policy.loader import load_json, validate_against_schema


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_one_receipt_bundle_correct_references() -> None:
    """One result receipt -> bundle with Observation and DiagnosticReport; no Specimen when no specimen receipts; references resolve."""
    receipts = [
        {
            "version": "0.1",
            "entity_type": "result",
            "specimen_id": None,
            "result_id": "R1",
            "accession_ids": [],
            "panel_id": "PANEL_K",
            "device_ids": ["DEV_CHEM_01"],
            "timestamps": {"result_generated": 300, "released": 400},
            "decision": "RELEASED",
            "reason_codes": [],
            "tokens": {"minted": [], "consumed": [], "revoked": []},
            "critical_comm_records": {"attempts": [], "ack_summary": []},
            "invariant_summary": {
                "violated_ids": [],
                "first_violation_ts": None,
                "final_status": "PASS",
            },
            "enforcement_summary": {
                "throttle": [],
                "kill_switch": [],
                "freeze_zone": [],
                "forensic_freeze": [],
            },
            "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
        },
    ]
    bundle = receipts_to_fhir_bundle(receipts)
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    entries = bundle["entry"]
    specimen_entries = [e for e in entries if e.get("resource", {}).get("resourceType") == "Specimen"]
    obs_entries = [e for e in entries if e.get("resource", {}).get("resourceType") == "Observation"]
    dr_entries = [e for e in entries if e.get("resource", {}).get("resourceType") == "DiagnosticReport"]
    assert len(specimen_entries) == 0, "No Specimen when no specimen receipts"
    assert len(obs_entries) == 1
    assert len(dr_entries) == 1
    obs = obs_entries[0]["resource"]
    assert "specimen" in obs
    assert "reference" not in obs["specimen"], "Missing specimen uses extension only, no reference"
    assert "extension" in obs["specimen"]
    dr = dr_entries[0]["resource"]
    assert "specimen" in dr
    assert len(dr["specimen"]) == 1 and "extension" in dr["specimen"][0]
    assert dr["result"][0]["reference"] == "#Observation/R1"
    assert dr["status"] == "final"
    errs = validate_bundle_structure(bundle)
    assert errs == [], errs
    serialized = json.dumps(bundle)
    assert "placeholder" not in serialized.lower(), "Exported bundle must not contain literal 'placeholder'"


def test_multiple_observations_per_diagnostic_report() -> None:
    """Multiple result receipts -> multiple Observations and DiagnosticReports; each DR references one Observation."""
    receipts = [
        {
            "version": "0.1",
            "entity_type": "specimen",
            "specimen_id": "S1",
            "result_id": None,
            "accession_ids": ["ACC1"],
            "panel_id": None,
            "device_ids": [],
            "timestamps": {"received": 100, "accepted": 200},
            "decision": "RELEASED",
            "reason_codes": [],
            "tokens": {"minted": [], "consumed": [], "revoked": []},
            "critical_comm_records": {"attempts": [], "ack_summary": []},
            "invariant_summary": {
                "violated_ids": [],
                "first_violation_ts": None,
                "final_status": "PASS",
            },
            "enforcement_summary": {
                "throttle": [],
                "kill_switch": [],
                "freeze_zone": [],
                "forensic_freeze": [],
            },
            "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
        },
        {
            "version": "0.1",
            "entity_type": "result",
            "specimen_id": None,
            "result_id": "R1",
            "panel_id": "PANEL_A",
            "device_ids": [],
            "timestamps": {},
            "decision": "RELEASED",
            "reason_codes": [],
            "tokens": {"minted": [], "consumed": [], "revoked": []},
            "critical_comm_records": {"attempts": [], "ack_summary": []},
            "invariant_summary": {
                "violated_ids": [],
                "first_violation_ts": None,
                "final_status": "PASS",
            },
            "enforcement_summary": {
                "throttle": [],
                "kill_switch": [],
                "freeze_zone": [],
                "forensic_freeze": [],
            },
            "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
        },
        {
            "version": "0.1",
            "entity_type": "result",
            "specimen_id": None,
            "result_id": "R2",
            "panel_id": "PANEL_B",
            "device_ids": [],
            "timestamps": {},
            "decision": "HELD",
            "reason_codes": [],
            "tokens": {"minted": [], "consumed": [], "revoked": []},
            "critical_comm_records": {"attempts": [], "ack_summary": []},
            "invariant_summary": {
                "violated_ids": [],
                "first_violation_ts": None,
                "final_status": "PASS",
            },
            "enforcement_summary": {
                "throttle": [],
                "kill_switch": [],
                "freeze_zone": [],
                "forensic_freeze": [],
            },
            "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
        },
    ]
    bundle = receipts_to_fhir_bundle(receipts)
    obs_entries = [e for e in bundle["entry"] if e.get("resource", {}).get("resourceType") == "Observation"]
    dr_entries = [e for e in bundle["entry"] if e.get("resource", {}).get("resourceType") == "DiagnosticReport"]
    assert len(obs_entries) == 2
    assert len(dr_entries) == 2
    assert dr_entries[0]["resource"]["result"][0]["reference"] == "#Observation/R1"
    assert dr_entries[1]["resource"]["result"][0]["reference"] == "#Observation/R2"
    assert dr_entries[1]["resource"]["status"] == "partial"
    errs = validate_bundle_structure(bundle)
    assert errs == [], errs


def test_critical_result_includes_interpretation_flag() -> None:
    """Result receipt with CRIT reason_code -> Observation has interpretation (Critical)."""
    receipts = [
        {
            "version": "0.1",
            "entity_type": "result",
            "specimen_id": None,
            "result_id": "R_CRIT",
            "panel_id": "K",
            "device_ids": [],
            "timestamps": {},
            "decision": "RELEASED",
            "reason_codes": ["CRIT_A"],
            "tokens": {"minted": [], "consumed": [], "revoked": []},
            "critical_comm_records": {"attempts": [], "ack_summary": []},
            "invariant_summary": {
                "violated_ids": [],
                "first_violation_ts": None,
                "final_status": "PASS",
            },
            "enforcement_summary": {
                "throttle": [],
                "kill_switch": [],
                "freeze_zone": [],
                "forensic_freeze": [],
            },
            "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
        },
    ]
    bundle = receipts_to_fhir_bundle(receipts)
    obs_entries = [e for e in bundle["entry"] if e.get("resource", {}).get("resourceType") == "Observation"]
    assert len(obs_entries) == 1
    obs = obs_entries[0]["resource"]
    assert "interpretation" in obs
    interp = obs["interpretation"]
    assert len(interp) >= 1
    assert any(
        c.get("code") == "CR" or "Critical" in str(c.get("display", ""))
        for cod in interp
        for c in (cod.get("coding") or [])
    )


def test_fhir_export_determinism() -> None:
    """Same receipts => identical bundle JSON (canonical ordering)."""
    receipts = [
        {
            "version": "0.1",
            "entity_type": "specimen",
            "specimen_id": "S1",
            "result_id": None,
            "accession_ids": ["A1"],
            "panel_id": None,
            "device_ids": [],
            "timestamps": {"received": 100},
            "decision": "RELEASED",
            "reason_codes": [],
            "tokens": {"minted": [], "consumed": [], "revoked": []},
            "critical_comm_records": {"attempts": [], "ack_summary": []},
            "invariant_summary": {
                "violated_ids": [],
                "first_violation_ts": None,
                "final_status": "PASS",
            },
            "enforcement_summary": {
                "throttle": [],
                "kill_switch": [],
                "freeze_zone": [],
                "forensic_freeze": [],
            },
            "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
        },
        {
            "version": "0.1",
            "entity_type": "result",
            "specimen_id": None,
            "result_id": "R1",
            "panel_id": "P1",
            "device_ids": [],
            "timestamps": {},
            "decision": "RELEASED",
            "reason_codes": [],
            "tokens": {"minted": [], "consumed": [], "revoked": []},
            "critical_comm_records": {"attempts": [], "ack_summary": []},
            "invariant_summary": {
                "violated_ids": [],
                "first_violation_ts": None,
                "final_status": "PASS",
            },
            "enforcement_summary": {
                "throttle": [],
                "kill_switch": [],
                "freeze_zone": [],
                "forensic_freeze": [],
            },
            "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
        },
    ]
    b1 = receipts_to_fhir_bundle(receipts)
    b2 = receipts_to_fhir_bundle(receipts)
    assert json.dumps(b1, sort_keys=True) == json.dumps(b2, sort_keys=True)


def test_partner_id_and_policy_fingerprint_in_bundle_meta() -> None:
    """partner_id in meta.tag, policy_fingerprint in meta.extension."""
    receipts = [
        {
            "version": "0.1",
            "entity_type": "result",
            "specimen_id": None,
            "result_id": "R1",
            "panel_id": "P1",
            "device_ids": [],
            "timestamps": {},
            "decision": "RELEASED",
            "reason_codes": [],
            "tokens": {"minted": [], "consumed": [], "revoked": []},
            "critical_comm_records": {"attempts": [], "ack_summary": []},
            "invariant_summary": {
                "violated_ids": [],
                "first_violation_ts": None,
                "final_status": "PASS",
            },
            "enforcement_summary": {
                "throttle": [],
                "kill_switch": [],
                "freeze_zone": [],
                "forensic_freeze": [],
            },
            "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
        },
    ]
    bundle = receipts_to_fhir_bundle(receipts, partner_id="hsl_like", policy_fingerprint="abc123")
    assert bundle.get("meta", {}).get("tag")
    tags = [t for t in bundle["meta"]["tag"] if t.get("system") == "http://labtrust.org/fhir/partner"]
    assert len(tags) == 1 and tags[0].get("code") == "hsl_like"
    exts = bundle.get("meta", {}).get("extension") or []
    fp_ext = [e for e in exts if "policy-fingerprint" in e.get("url", "")]
    assert len(fp_ext) == 1 and fp_ext[0].get("valueString") == "abc123"


def test_validate_bundle_structure_required_keys() -> None:
    """validate_bundle_structure rejects bundle without resourceType/type/entry."""
    errs = validate_bundle_structure({})
    assert any("Bundle" in e or "resourceType" in e for e in errs)
    errs2 = validate_bundle_structure({"resourceType": "Bundle", "type": "collection", "entry": []})
    assert errs2 == []


def test_fhir_bundle_export_schema_validation() -> None:
    """Exported bundle validates against policy/schemas/fhir_bundle_export.v0.1.schema.json."""
    root = _repo_root()
    schema_path = root / "policy" / "schemas" / "fhir_bundle_export.v0.1.schema.json"
    if not schema_path.exists():
        pytest.skip("fhir_bundle_export.v0.1.schema.json not found")
    schema = load_json(schema_path)
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"fullUrl": "#Specimen/S1", "resource": {"resourceType": "Specimen", "id": "S1"}},
            {"fullUrl": "#Observation/R1", "resource": {"resourceType": "Observation", "id": "R1"}},
            {
                "fullUrl": "#DiagnosticReport/R1",
                "resource": {"resourceType": "DiagnosticReport", "id": "R1"},
            },
        ],
    }
    validate_against_schema(bundle, schema, schema_path)


def test_export_fhir_from_receipts_dir(tmp_path: Path) -> None:
    """export_fhir loads receipts from dir and writes valid bundle."""
    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir()
    (receipts_dir / "receipt_result_R1.v0.1.json").write_text(
        json.dumps(
            {
                "version": "0.1",
                "entity_type": "result",
                "specimen_id": None,
                "result_id": "R1",
                "panel_id": "P1",
                "device_ids": [],
                "timestamps": {},
                "decision": "RELEASED",
                "reason_codes": [],
                "tokens": {"minted": [], "consumed": [], "revoked": []},
                "critical_comm_records": {"attempts": [], "ack_summary": []},
                "invariant_summary": {
                    "violated_ids": [],
                    "first_violation_ts": None,
                    "final_status": "PASS",
                },
                "enforcement_summary": {
                    "throttle": [],
                    "kill_switch": [],
                    "freeze_zone": [],
                    "forensic_freeze": [],
                },
                "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    out_path = export_fhir(receipts_dir, out_dir)
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["resourceType"] == "Bundle"
    assert data["type"] == "collection"
    assert validate_bundle_structure(data) == []


def test_fhir_export_valid_r4_json_no_placeholder() -> None:
    """Produced JSON parses; Bundle.type and resourceType present; references resolve; no literal 'placeholder'."""
    receipts = [
        {
            "version": "0.1",
            "entity_type": "specimen",
            "specimen_id": "S1",
            "result_id": None,
            "accession_ids": ["ACC1"],
            "panel_id": None,
            "device_ids": [],
            "timestamps": {"received": 100},
            "decision": "RELEASED",
            "reason_codes": [],
            "tokens": {"minted": [], "consumed": [], "revoked": []},
            "critical_comm_records": {"attempts": [], "ack_summary": []},
            "invariant_summary": {
                "violated_ids": [],
                "first_violation_ts": None,
                "final_status": "PASS",
            },
            "enforcement_summary": {
                "throttle": [],
                "kill_switch": [],
                "freeze_zone": [],
                "forensic_freeze": [],
            },
            "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
        },
        {
            "version": "0.1",
            "entity_type": "result",
            "specimen_id": None,
            "result_id": "R1",
            "panel_id": "P1",
            "device_ids": [],
            "timestamps": {},
            "decision": "RELEASED",
            "reason_codes": [],
            "tokens": {"minted": [], "consumed": [], "revoked": []},
            "critical_comm_records": {"attempts": [], "ack_summary": []},
            "invariant_summary": {
                "violated_ids": [],
                "first_violation_ts": None,
                "final_status": "PASS",
            },
            "enforcement_summary": {
                "throttle": [],
                "kill_switch": [],
                "freeze_zone": [],
                "forensic_freeze": [],
            },
            "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
        },
    ]
    bundle = receipts_to_fhir_bundle(receipts)
    # Round-trip: parse produced JSON
    serialized = json.dumps(bundle, sort_keys=True)
    parsed = json.loads(serialized)
    assert parsed.get("resourceType") == "Bundle"
    assert parsed.get("type") == "collection"
    for i, e in enumerate(parsed.get("entry") or []):
        r = e.get("resource") or {}
        assert "resourceType" in r, f"entry[{i}].resource must have resourceType"
        assert "id" in r, f"entry[{i}].resource must have id"
    errs = validate_bundle_structure(parsed)
    assert errs == [], errs
    assert "placeholder" not in serialized.lower(), "Exported FHIR JSON must not contain literal 'placeholder'"


# --- Deterministic, offline tests for Option B (data-absent-reason) and no placeholders ---

DATA_ABSENT_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/data-absent-reason"
DATA_ABSENT_CODESYSTEM = "http://terminology.hl7.org/CodeSystem/data-absent-reason"


def _minimal_result_receipt(result_id: str = "R1") -> dict:
    return {
        "version": "0.1",
        "entity_type": "result",
        "specimen_id": None,
        "result_id": result_id,
        "panel_id": "PANEL_K",
        "device_ids": [],
        "timestamps": {},
        "decision": "RELEASED",
        "reason_codes": [],
        "tokens": {"minted": [], "consumed": [], "revoked": []},
        "critical_comm_records": {"attempts": [], "ack_summary": []},
        "invariant_summary": {
            "violated_ids": [],
            "first_violation_ts": None,
            "final_status": "PASS",
        },
        "enforcement_summary": {
            "throttle": [],
            "kill_switch": [],
            "freeze_zone": [],
            "forensic_freeze": [],
        },
        "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
    }


def test_missing_specimen_uses_extension() -> None:
    """When specimen is absent: no Specimen resource; Observation.specimen has only data-absent-reason extension; no placeholder anywhere."""
    receipts = [_minimal_result_receipt()]
    bundle = receipts_to_fhir_bundle(receipts)
    serialized = json.dumps(bundle)
    assert "placeholder" not in serialized.lower(), "No string 'placeholder' in exported JSON"
    for e in bundle.get("entry") or []:
        r = e.get("resource") or {}
        assert r.get("id") != "placeholder", f"Resource id must not be placeholder: {r.get('resourceType')}"
        assert "placeholder" not in (r.get("id") or "").lower()
    specimen_entries = [e for e in bundle["entry"] if (e.get("resource") or {}).get("resourceType") == "Specimen"]
    assert len(specimen_entries) == 0, "No Specimen resource when specimen absent"
    obs_entries = [e for e in bundle["entry"] if (e.get("resource") or {}).get("resourceType") == "Observation"]
    assert len(obs_entries) >= 1
    for obs_resource in [e["resource"] for e in obs_entries]:
        assert "specimen" in obs_resource
        specimen = obs_resource["specimen"]
        assert specimen.get("reference") is None or specimen.get("reference") == "", "reference must be absent"
        exts = specimen.get("extension") or []
        assert any(
            ext.get("url") == DATA_ABSENT_EXTENSION_URL and ext.get("valueCode") == "unknown"
            for ext in exts
        ), "Observation.specimen must contain data-absent-reason extension with valueCode unknown"
    assert validate_bundle_structure(bundle) == []


def test_present_specimen_resolves() -> None:
    """When specimen exists: Specimen resource with non-placeholder id; Observation.specimen.reference resolves in bundle."""
    receipts = [
        {
            "version": "0.1",
            "entity_type": "specimen",
            "specimen_id": "S1",
            "result_id": None,
            "accession_ids": ["ACC1"],
            "panel_id": None,
            "device_ids": [],
            "timestamps": {"received": 100},
            "decision": "RELEASED",
            "reason_codes": [],
            "tokens": {"minted": [], "consumed": [], "revoked": []},
            "critical_comm_records": {"attempts": [], "ack_summary": []},
            "invariant_summary": {"violated_ids": [], "first_violation_ts": None, "final_status": "PASS"},
            "enforcement_summary": {"throttle": [], "kill_switch": [], "freeze_zone": [], "forensic_freeze": []},
            "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
        },
        _minimal_result_receipt("R1"),
    ]
    bundle = receipts_to_fhir_bundle(receipts)
    serialized = json.dumps(bundle)
    assert "placeholder" not in serialized.lower()
    specimen_entries = [e for e in bundle["entry"] if (e.get("resource") or {}).get("resourceType") == "Specimen"]
    assert len(specimen_entries) == 1
    spec = specimen_entries[0]["resource"]
    spec_id = spec["id"]
    assert spec_id != "placeholder" and "placeholder" not in (spec_id or "").lower()
    obs_entries = [e for e in bundle["entry"] if (e.get("resource") or {}).get("resourceType") == "Observation"]
    for obs_resource in [e["resource"] for e in obs_entries]:
        assert "specimen" in obs_resource
        ref = obs_resource["specimen"].get("reference")
        assert ref == f"#Specimen/{spec_id}", f"Observation.specimen.reference must resolve to Specimen in bundle: {ref}"
    full_urls = {e.get("fullUrl") for e in bundle["entry"] if e.get("fullUrl")}
    assert f"#Specimen/{spec_id}" in full_urls
    assert validate_bundle_structure(bundle) == []


def test_missing_numeric_value_uses_data_absent_reason() -> None:
    """Observation with no numeric value: value[x] absent; dataAbsentReason with correct coding."""
    receipts = [_minimal_result_receipt()]
    bundle = receipts_to_fhir_bundle(receipts)
    obs_entries = [e for e in bundle["entry"] if (e.get("resource") or {}).get("resourceType") == "Observation"]
    assert len(obs_entries) == 1
    obs = obs_entries[0]["resource"]
    assert "valueQuantity" not in obs
    assert "valueString" not in obs
    assert "dataAbsentReason" in obs
    dar = obs["dataAbsentReason"]
    codings = dar.get("coding") or []
    assert any(
        c.get("system") == DATA_ABSENT_CODESYSTEM and c.get("code") == "unknown" for c in codings
    ), "dataAbsentReason must have coding with system and code unknown"
