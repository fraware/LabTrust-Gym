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
    load_receipts_from_dir,
    receipts_to_fhir_bundle,
    validate_bundle_structure,
    export_fhir,
)
from labtrust_gym.policy.loader import load_json, validate_against_schema


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_one_receipt_bundle_correct_references() -> None:
    """One result receipt -> bundle with Specimen (placeholder), Observation, DiagnosticReport; references resolve."""
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
            "invariant_summary": {"violated_ids": [], "first_violation_ts": None, "final_status": "PASS"},
            "enforcement_summary": {"throttle": [], "kill_switch": [], "freeze_zone": [], "forensic_freeze": []},
            "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
        },
    ]
    bundle = receipts_to_fhir_bundle(receipts)
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    entries = bundle["entry"]
    assert len(entries) >= 3  # Specimen (placeholder), Observation, DiagnosticReport
    specimen_entries = [e for e in entries if e.get("resource", {}).get("resourceType") == "Specimen"]
    obs_entries = [e for e in entries if e.get("resource", {}).get("resourceType") == "Observation"]
    dr_entries = [e for e in entries if e.get("resource", {}).get("resourceType") == "DiagnosticReport"]
    assert len(specimen_entries) == 1
    assert len(obs_entries) == 1
    assert len(dr_entries) == 1
    dr = dr_entries[0]["resource"]
    assert dr["specimen"][0]["reference"] == "#Specimen/placeholder"
    assert dr["result"][0]["reference"] == "#Observation/R1"
    assert dr["status"] == "final"
    errs = validate_bundle_structure(bundle)
    assert errs == [], errs


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
            "invariant_summary": {"violated_ids": [], "first_violation_ts": None, "final_status": "PASS"},
            "enforcement_summary": {"throttle": [], "kill_switch": [], "freeze_zone": [], "forensic_freeze": []},
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
            "invariant_summary": {"violated_ids": [], "first_violation_ts": None, "final_status": "PASS"},
            "enforcement_summary": {"throttle": [], "kill_switch": [], "freeze_zone": [], "forensic_freeze": []},
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
            "invariant_summary": {"violated_ids": [], "first_violation_ts": None, "final_status": "PASS"},
            "enforcement_summary": {"throttle": [], "kill_switch": [], "freeze_zone": [], "forensic_freeze": []},
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
            "invariant_summary": {"violated_ids": [], "first_violation_ts": None, "final_status": "PASS"},
            "enforcement_summary": {"throttle": [], "kill_switch": [], "freeze_zone": [], "forensic_freeze": []},
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
        for cod in interp for c in (cod.get("coding") or [])
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
            "invariant_summary": {"violated_ids": [], "first_violation_ts": None, "final_status": "PASS"},
            "enforcement_summary": {"throttle": [], "kill_switch": [], "freeze_zone": [], "forensic_freeze": []},
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
            "invariant_summary": {"violated_ids": [], "first_violation_ts": None, "final_status": "PASS"},
            "enforcement_summary": {"throttle": [], "kill_switch": [], "freeze_zone": [], "forensic_freeze": []},
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
            "invariant_summary": {"violated_ids": [], "first_violation_ts": None, "final_status": "PASS"},
            "enforcement_summary": {"throttle": [], "kill_switch": [], "freeze_zone": [], "forensic_freeze": []},
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
            {"fullUrl": "#DiagnosticReport/R1", "resource": {"resourceType": "DiagnosticReport", "id": "R1"}},
        ],
    }
    validate_against_schema(bundle, schema, schema_path)


def test_export_fhir_from_receipts_dir(tmp_path: Path) -> None:
    """export_fhir loads receipts from dir and writes valid bundle."""
    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir()
    (receipts_dir / "receipt_result_R1.v0.1.json").write_text(
        json.dumps({
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
            "invariant_summary": {"violated_ids": [], "first_violation_ts": None, "final_status": "PASS"},
            "enforcement_summary": {"throttle": [], "kill_switch": [], "freeze_zone": [], "forensic_freeze": []},
            "hashchain": {"head_hash": "h", "last_event_hash": "e", "length": 1},
        }, sort_keys=True),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    out_path = export_fhir(receipts_dir, out_dir)
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["resourceType"] == "Bundle"
    assert data["type"] == "collection"
    assert validate_bundle_structure(data) == []
