"""
Receipt and Evidence Bundle export: determinism, schema validation, receipt coverage.

- Deterministic: same episode log => identical EvidenceBundle.v0.1 output.
- Schema: exported receipts and manifest validate against policy/schemas.
- Coverage: release, hold, reject, blocked, forensic freeze cases produce expected receipts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.export.receipts import (
    build_receipt,
    build_receipts_from_log,
    export_receipts,
    load_episode_log,
    write_evidence_bundle,
)
from labtrust_gym.policy.loader import load_json, validate_against_schema


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_load_episode_log_empty() -> None:
    """Empty file => empty list."""
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        path = Path(f.name)
    try:
        entries = load_episode_log(path)
        assert entries == []
    finally:
        path.unlink(missing_ok=True)


def test_load_episode_log_one_line() -> None:
    """One JSONL line => one entry."""
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write('{"t_s": 0, "agent_id": "A", "action_type": "TICK", "status": "ACCEPTED"}\n')
        path = Path(f.name)
    try:
        entries = load_episode_log(path)
        assert len(entries) == 1
        assert entries[0]["t_s"] == 0
        assert entries[0]["action_type"] == "TICK"
    finally:
        path.unlink(missing_ok=True)


def test_build_receipts_from_log_specimen_and_result() -> None:
    """Log with CREATE_ACCESSION + GENERATE_RESULT + RELEASE_RESULT => specimen and result receipts."""
    entries = [
        {
            "t_s": 100,
            "agent_id": "A",
            "action_type": "CREATE_ACCESSION",
            "args": {"specimen_id": "S1"},
            "status": "ACCEPTED",
            "hashchain": {"head_hash": "h0", "length": 1, "last_event_hash": "e0"},
        },
        {
            "t_s": 200,
            "agent_id": "A",
            "action_type": "ACCEPT_SPECIMEN",
            "args": {"specimen_id": "S1"},
            "status": "ACCEPTED",
            "hashchain": {"head_hash": "h1", "length": 2, "last_event_hash": "e1"},
        },
        {
            "t_s": 300,
            "agent_id": "A",
            "action_type": "GENERATE_RESULT",
            "args": {"result_id": "R1", "specimen_id": "S1", "panel_id": "PANEL_A"},
            "status": "ACCEPTED",
            "hashchain": {"head_hash": "h2", "length": 3, "last_event_hash": "e2"},
        },
        {
            "t_s": 400,
            "agent_id": "A",
            "action_type": "RELEASE_RESULT",
            "args": {"result_id": "R1"},
            "status": "ACCEPTED",
            "hashchain": {"head_hash": "h3", "length": 4, "last_event_hash": "e3"},
        },
    ]
    receipts = build_receipts_from_log(entries)
    assert len(receipts) == 2
    spec_r = next(r for r in receipts if r.get("entity_type") == "specimen" and r.get("specimen_id") == "S1")
    res_r = next(r for r in receipts if r.get("entity_type") == "result" and r.get("result_id") == "R1")
    assert spec_r["decision"] == "RELEASED"
    assert spec_r["timestamps"].get("received") == 100
    assert spec_r["timestamps"].get("accepted") == 200
    assert res_r["decision"] == "RELEASED"
    assert res_r["timestamps"].get("result_generated") == 300
    assert res_r["timestamps"].get("released") == 400
    assert res_r["panel_id"] == "PANEL_A"


def test_receipt_hold() -> None:
    """HOLD_SPECIMEN / HOLD_RESULT => decision HELD."""
    entries = [
        {
            "t_s": 100,
            "action_type": "CREATE_ACCESSION",
            "args": {"specimen_id": "S_H"},
            "status": "ACCEPTED",
        },
        {
            "t_s": 200,
            "action_type": "HOLD_SPECIMEN",
            "args": {"specimen_id": "S_H"},
            "status": "ACCEPTED",
        },
    ]
    receipts = build_receipts_from_log(entries)
    spec = next(r for r in receipts if r.get("specimen_id") == "S_H")
    assert spec["decision"] == "HELD"


def test_receipt_reject() -> None:
    """REJECT_SPECIMEN => decision REJECTED."""
    entries = [
        {
            "t_s": 100,
            "action_type": "CREATE_ACCESSION",
            "args": {"specimen_id": "S_R"},
            "status": "ACCEPTED",
        },
        {
            "t_s": 200,
            "action_type": "REJECT_SPECIMEN",
            "args": {"specimen_id": "S_R"},
            "status": "ACCEPTED",
        },
    ]
    receipts = build_receipts_from_log(entries)
    spec = next(r for r in receipts if r.get("specimen_id") == "S_R")
    assert spec["decision"] == "REJECTED"


def test_receipt_blocked() -> None:
    """BLOCKED status on last relevant step => decision BLOCKED."""
    entries = [
        {
            "t_s": 100,
            "action_type": "CREATE_ACCESSION",
            "args": {"specimen_id": "S_B"},
            "status": "ACCEPTED",
        },
        {
            "t_s": 200,
            "action_type": "RELEASE_RESULT",
            "args": {"result_id": "R_B"},
            "status": "BLOCKED",
            "blocked_reason_code": "CRIT_NO_ACK",
        },
    ]
    receipts = build_receipts_from_log(entries)
    res = next(r for r in receipts if r.get("result_id") == "R_B")
    assert res["decision"] == "BLOCKED"
    assert "CRIT_NO_ACK" in res["reason_codes"]


def test_receipt_security_event_reflected() -> None:
    """
    Episode log with BLOCKED + security reason code (SECURITY_REASON_CODES) produces
    receipt that reflects the block (decision BLOCKED, reason code in reason_codes).
    """
    from labtrust_gym.benchmarks.metrics import SECURITY_REASON_CODES

    reason_code = "SIG_INVALID"
    assert reason_code in SECURITY_REASON_CODES
    entries = [
        {
            "t_s": 100,
            "action_type": "CREATE_ACCESSION",
            "args": {"specimen_id": "S_SEC"},
            "status": "ACCEPTED",
        },
        {
            "t_s": 200,
            "action_type": "RELEASE_RESULT",
            "args": {"result_id": "R_SEC"},
            "status": "BLOCKED",
            "blocked_reason_code": reason_code,
        },
    ]
    receipts = build_receipts_from_log(entries)
    res = next(r for r in receipts if r.get("result_id") == "R_SEC")
    assert res["decision"] == "BLOCKED"
    assert reason_code in res["reason_codes"]


def test_receipt_forensic_freeze_hashchain() -> None:
    """Step with FORENSIC_FREEZE_LOG emit => hashchain break_status broken in proof."""
    entries = [
        {
            "t_s": 100,
            "action_type": "TICK",
            "args": {},
            "status": "ACCEPTED",
            "emits": ["FORENSIC_FREEZE_LOG"],
            "hashchain": {"head_hash": "h", "length": 1, "last_event_hash": "e"},
        },
    ]
    from labtrust_gym.export.receipts import _hashchain_from_entries

    hc = _hashchain_from_entries(entries)
    assert hc.get("break_status") == "broken"
    # Receipt uses same hashchain; build_receipt with fallback
    r = build_receipt("specimen", "S1", entries, hc)
    assert r["hashchain"].get("break_status") in ("intact", "broken")


def test_receipt_schema_validation() -> None:
    """Exported receipt validates against policy/schemas/receipt.v0.1.schema.json."""
    root = _repo_root()
    schema_path = root / "policy" / "schemas" / "receipt.v0.1.schema.json"
    if not schema_path.exists():
        pytest.skip("receipt.v0.1.schema.json not found")
    schema = load_json(schema_path)
    receipt = {
        "version": "0.1",
        "entity_type": "specimen",
        "specimen_id": "S1",
        "result_id": None,
        "accession_ids": [],
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
    }
    validate_against_schema(receipt, schema, schema_path)


def test_manifest_schema_validation() -> None:
    """Evidence bundle manifest validates against evidence_bundle_manifest.v0.1.schema.json."""
    root = _repo_root()
    schema_path = root / "policy" / "schemas" / "evidence_bundle_manifest.v0.1.schema.json"
    if not schema_path.exists():
        pytest.skip("evidence_bundle_manifest.v0.1.schema.json not found")
    schema = load_json(schema_path)
    manifest = {
        "version": "0.1",
        "files": [{"path": "receipt_specimen_S1.v0.1.json", "sha256": "abc"}],
        "policy_fingerprint": None,
        "partner_id": None,
        "signature": None,
    }
    validate_against_schema(manifest, schema, schema_path)


def test_export_determinism() -> None:
    """Same episode log => identical EvidenceBundle output (file contents and manifest hashes)."""
    import tempfile

    entries = [
        {
            "t_s": 100,
            "agent_id": "A",
            "action_type": "CREATE_ACCESSION",
            "args": {"specimen_id": "S1"},
            "status": "ACCEPTED",
            "hashchain": {"head_hash": "h0", "length": 1, "last_event_hash": "e0"},
        },
        {
            "t_s": 200,
            "agent_id": "A",
            "action_type": "RELEASE_RESULT",
            "args": {"result_id": "R1"},
            "status": "ACCEPTED",
            "hashchain": {"head_hash": "h1", "length": 2, "last_event_hash": "e1"},
        },
    ]
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "ep.jsonl"
        with log_path.open("w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, sort_keys=True) + "\n")
        out1 = Path(tmp) / "out1"
        out2 = Path(tmp) / "out2"
        b1 = export_receipts(log_path, out1)
        b2 = export_receipts(log_path, out2)
        assert b1.name == "EvidenceBundle.v0.1"
        assert b2.name == "EvidenceBundle.v0.1"
        files1 = sorted(b1.iterdir())
        files2 = sorted(b2.iterdir())
        assert [f.name for f in files1] == [f.name for f in files2]
        for f1, f2 in zip(files1, files2):
            assert f1.read_text(encoding="utf-8") == f2.read_text(encoding="utf-8"), f"Content diff: {f1.name}"


def test_evidence_bundle_manifest_has_tool_registry_fingerprint() -> None:
    """R-DATA-001/SEC-DATA-PROV-001: Export with policy_root yields manifest with tool_registry_fingerprint."""
    import tempfile

    root = _repo_root()
    entries = [
        {
            "t_s": 10,
            "agent_id": "A",
            "action_type": "CREATE_ACCESSION",
            "args": {"specimen_id": "S1"},
            "status": "ACCEPTED",
        },
    ]
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "episode_log.jsonl"
        with log_path.open("w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, sort_keys=True) + "\n")
        out = Path(tmp) / "export"
        bundle = export_receipts(log_path, out, policy_root=root, partner_id="test_partner")
        manifest_path = bundle / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "tool_registry_fingerprint" in manifest
        if (root / "policy" / "tool_registry.v0.1.yaml").exists():
            assert isinstance(manifest["tool_registry_fingerprint"], str)


def test_write_evidence_bundle_creates_manifest() -> None:
    """write_evidence_bundle creates manifest.json with files + sha256 and policy_fingerprint."""
    import tempfile

    receipts = [
        {
            "version": "0.1",
            "entity_type": "specimen",
            "specimen_id": "S1",
            "result_id": None,
            "accession_ids": [],
            "panel_id": None,
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
    ]
    entries = [
        {
            "t_s": 0,
            "action_type": "CREATE_ACCESSION",
            "args": {"specimen_id": "S1"},
            "status": "ACCEPTED",
        }
    ]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "export"
        bundle = write_evidence_bundle(out, receipts, entries, policy_fingerprint="fp123", partner_id=None)
        manifest_path = bundle / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["version"] == "0.1"
        assert manifest["policy_fingerprint"] == "fp123"
        assert len(manifest["files"]) >= 1
        for f in manifest["files"]:
            assert "path" in f and "sha256" in f


def test_write_evidence_bundle_real_signing_and_verify_receipt() -> None:
    """Real Ed25519 signing via get_private_key callback; verify_receipt and verify_manifest_signature pass."""
    pytest.importorskip("cryptography")
    import base64
    import tempfile

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from labtrust_gym.engine.signatures import (
        verify_manifest_signature,
        verify_receipt,
    )

    priv = Ed25519PrivateKey.generate()
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pub_b64 = base64.b64encode(pub_raw).decode("ascii")
    priv_raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_id = "ed25519:key_bundle_test"
    key_registry = {
        "version": "0.1",
        "keys": [
            {
                "key_id": key_id,
                "public_key": pub_b64,
                "agent_id": "SYSTEM",
                "role_id": "R_SYSTEM_CONTROL",
                "status": "ACTIVE",
                "not_before_ts_s": None,
                "not_after_ts_s": None,
            },
        ],
    }

    def get_private_key(kid: str) -> bytes | None:
        if kid == key_id:
            return priv_raw
        return None

    receipts = [
        {
            "version": "0.1",
            "entity_type": "specimen",
            "specimen_id": "S1",
            "result_id": None,
            "accession_ids": [],
            "panel_id": None,
            "device_ids": [],
            "timestamps": {},
            "decision": "RELEASED",
            "reason_codes": [],
            "tokens": {"minted": [], "consumed": [], "revoked": []},
            "critical_comm_records": {"attempts": [], "ack_summary": []},
            "invariant_summary": {"violated_ids": [], "first_violation_ts": None, "final_status": "PASS"},
            "enforcement_summary": {"throttle": [], "kill_switch": [], "freeze_zone": [], "forensic_freeze": []},
            "hashchain": {"head_hash": "", "last_event_hash": "", "length": 0, "break_status": "intact"},
        },
    ]
    entries: list[dict] = []

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "signed"
        bundle_dir = write_evidence_bundle(
            out,
            receipts,
            entries,
            policy_fingerprint="fp",
            partner_id=None,
            sign_bundle=True,
            get_private_key=get_private_key,
            sign_key_id=key_id,
            key_registry=key_registry,
        )
        manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
        assert isinstance(manifest.get("signature"), dict)
        assert manifest["signature"].get("algorithm") == "ed25519"
        assert "signature_b64" in manifest["signature"] and "public_key_b64" in manifest["signature"]
        ok, err = verify_manifest_signature(manifest, key_registry)
        assert ok, err

        receipt_path = bundle_dir / "receipt_specimen_S1.v0.1.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert isinstance(receipt.get("signature"), dict)
        ok, err = verify_receipt(receipt, key_registry)
        assert ok, err


def test_receipt_tampering_fails_verification() -> None:
    """Tampering with a signed receipt causes verify_receipt to fail."""
    pytest.importorskip("cryptography")
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from labtrust_gym.engine.signatures import canonical_for_signing, sign_payload_bytes, verify_receipt

    priv = Ed25519PrivateKey.generate()
    pub_b64 = base64.b64encode(
        priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
    priv_raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_id = "ed25519:key_tamper_test"
    key_registry = {"version": "0.1", "keys": [{"key_id": key_id, "public_key": pub_b64, "status": "ACTIVE"}]}
    receipt = {"version": "0.1", "entity_type": "result", "result_id": "R1", "decision": "RELEASED"}
    payload = canonical_for_signing(receipt)
    sig_b64 = sign_payload_bytes(payload, priv_raw)
    receipt["signature"] = {
        "algorithm": "ed25519",
        "public_key_b64": pub_b64,
        "signature_b64": sig_b64,
        "key_id": key_id,
    }
    ok, _ = verify_receipt(receipt, key_registry)
    assert ok
    receipt["decision"] = "REJECTED"
    ok, reason = verify_receipt(receipt, key_registry)
    assert not ok
    assert reason is not None
