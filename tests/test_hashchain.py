"""
Unit tests for audit hashchain and forensic freeze; integration test for GS-022.

- Audit log: canonical serialization, sha256 chaining, append, fault injection.
- CoreEnv: reset, step contract, query system_state('log_frozen'), last_reason_code_system.
- GS-022: run scenario only when LABTRUST_RUN_GOLDEN=1 using CoreEnv.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import asdict

import jsonschema
import pytest

from labtrust_gym.engine.audit_log import (
    AuditLog,
    canonical_serialize,
    hash_event,
)
from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.runner import GoldenRunner


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ---- Unit: canonical serialization ----
def test_canonical_serialize_sorted_keys() -> None:
    event = {"event_id": "e1", "action_type": "A", "t_s": 1}
    raw = canonical_serialize(event)
    parsed = json.loads(raw.decode("utf-8"))
    keys = list(parsed.keys())
    assert keys == sorted(keys)


def test_canonical_serialize_deterministic() -> None:
    event = {"z": 3, "a": 1, "m": 2}
    a = canonical_serialize(event)
    b = canonical_serialize(event)
    assert a == b


# ---- Unit: hash ----
def test_hash_event_deterministic() -> None:
    prev = "abc"
    payload = b'{"a":1}'
    a = hash_event(prev, payload)
    b = hash_event(prev, payload)
    assert a == b
    assert len(a) == 64
    assert all(c in "0123456789abcdef" for c in a)


def test_hash_event_different_prev_different_hash() -> None:
    payload = b'{"a":1}'
    h1 = hash_event("prev1", payload)
    h2 = hash_event("prev2", payload)
    assert h1 != h2


# ---- Unit: AuditLog append ----
def test_audit_log_append_empty_starts_chain() -> None:
    log = AuditLog()
    event = {"event_id": "e1", "action_type": "CREATE_ACCESSION"}
    out, broken = log.append(event)
    assert broken is False
    assert out["length"] == 1
    assert out["head_hash"] == out["last_event_hash"]
    assert len(out["head_hash"]) == 64


def test_audit_log_append_chains() -> None:
    log = AuditLog()
    log.append({"event_id": "e1", "action_type": "A"})
    out2, _ = log.append({"event_id": "e2", "action_type": "B"})
    assert out2["length"] == 2
    assert out2["head_hash"] != out2["last_event_hash"]


def test_audit_log_fault_injection_breaks_chain() -> None:
    log = AuditLog(fault_injection={"break_hash_prev_on_event_id": "e2"})
    log.append({"event_id": "e1", "action_type": "A"})
    out2, broken = log.append({"event_id": "e2", "action_type": "B"})
    assert broken is True
    assert out2["length"] == 2


# ---- Unit: CoreEnv ----
def test_core_env_reset_step_query() -> None:
    env = CoreEnv()
    env.reset(
        {"system": {}, "specimens": [], "tokens": []},
        deterministic=True,
        rng_seed=42,
    )
    out = env.step({
        "event_id": "e1",
        "t_s": 8000,
        "agent_id": "A_RECEPTION",
        "action_type": "CREATE_ACCESSION",
        "args": {"specimen_id": "S1"},
        "reason_code": None,
        "token_refs": [],
    })
    assert out["status"] == "ACCEPTED"
    assert "CREATE_ACCESSION" in out["emits"]
    assert out["hashchain"]["length"] == 1
    assert env.query("system_state('log_frozen')") is False


def test_core_env_forensic_freeze_blocks_further_steps() -> None:
    env = CoreEnv()
    env.reset(
        {
            "system": {},
            "specimens": [],
            "tokens": [],
            "audit_fault_injection": {"break_hash_prev_on_event_id": "e2"},
        },
        deterministic=True,
        rng_seed=42,
    )
    env.step({
        "event_id": "e1",
        "t_s": 8000,
        "agent_id": "A_RECEPTION",
        "action_type": "CREATE_ACCESSION",
        "args": {"specimen_id": "S1"},
        "reason_code": None,
        "token_refs": [],
    })
    out2 = env.step({
        "event_id": "e2",
        "t_s": 8010,
        "agent_id": "A_RECEPTION",
        "action_type": "ACCEPT_SPECIMEN",
        "args": {"specimen_id": "S1"},
        "reason_code": None,
        "token_refs": [],
    })
    assert out2["status"] == "ACCEPTED"
    assert "FORENSIC_FREEZE_LOG" in out2["emits"]
    assert env.query("system_state('log_frozen')") is True
    assert env.query("last_reason_code_system") == "AUDIT_CHAIN_BROKEN"

    out3 = env.step({
        "event_id": "e3",
        "t_s": 8020,
        "agent_id": "A_RECEPTION",
        "action_type": "MOVE",
        "args": {"entity_type": "Agent", "entity_id": "A_RECEPTION", "from_zone": "Z_SRA_RECEPTION", "to_zone": "Z_ACCESSIONING"},
        "reason_code": None,
        "token_refs": [],
    })
    assert out3["status"] == "BLOCKED"
    assert out3["blocked_reason_code"] == "AUDIT_CHAIN_BROKEN"


# ---- Integration: GS-022 only ----
def _should_run_golden() -> bool:
    return os.environ.get("LABTRUST_RUN_GOLDEN") == "1"


# GS-022 scenario: hash chain broken triggers forensic freeze (embedded to avoid YAML parse issues).
GS022_SCENARIO = {
    "scenario_id": "GS-022",
    "title": "Audit: hash chain broken triggers forensic freeze (no further actions permitted)",
    "initial_state": {
        "system": {"now_s": 0, "downtime_active": False},
        "specimens": [],
        "tokens": [],
        "audit_fault_injection": {"break_hash_prev_on_event_id": "e2"},
    },
    "script": [
        {
            "event_id": "e1",
            "t_s": 8000,
            "agent_id": "A_RECEPTION",
            "action_type": "CREATE_ACCESSION",
            "args": {"specimen_id": "S1"},
            "reason_code": None,
            "token_refs": [],
            "expect": {"status": "ACCEPTED"},
        },
        {
            "event_id": "e2",
            "t_s": 8010,
            "agent_id": "A_RECEPTION",
            "action_type": "ACCEPT_SPECIMEN",
            "args": {"specimen_id": "S1"},
            "reason_code": None,
            "token_refs": [],
            "expect": {
                "status": "ACCEPTED",
                "emits": ["FORENSIC_FREEZE_LOG"],
                "state_assertions": [
                    "system_state('log_frozen') == 'True'",
                    "last_reason_code_system == 'AUDIT_CHAIN_BROKEN'",
                ],
            },
        },
        {
            "event_id": "e3",
            "t_s": 8020,
            "agent_id": "A_RECEPTION",
            "action_type": "MOVE",
            "args": {
                "entity_type": "Agent",
                "entity_id": "A_RECEPTION",
                "from_zone": "Z_SRA_RECEPTION",
                "to_zone": "Z_ACCESSIONING",
            },
            "reason_code": None,
            "token_refs": [],
            "expect": {
                "status": "BLOCKED",
                "blocked_reason_code": "AUDIT_CHAIN_BROKEN",
            },
        },
    ],
}


def test_gs022_hashchain_forensic_freeze() -> None:
    """
    Run only GS-022: hash chain broken triggers forensic freeze.
    Uses CoreEnv. Skipped unless LABTRUST_RUN_GOLDEN=1.
    """
    if not _should_run_golden():
        pytest.skip("Set LABTRUST_RUN_GOLDEN=1 to run GS-022 integration.")

    root = _repo_root()
    schema_path = root / "policy" / "schemas" / "runner_output_contract.v0.1.schema.json"
    if not schema_path.exists():
        schema_path = root / "runner_output_contract.v0.1.schema.json"
    if not schema_path.exists():
        pytest.fail(f"Schema not found: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    if not emits_path.exists():
        emits_path = root / "emits_vocab.v0.1.yaml"
    if not emits_path.exists():
        pytest.fail(f"Emits vocab not found: {emits_path}")

    env = CoreEnv()
    runner = GoldenRunner(env, emits_vocab_path=str(emits_path))
    report = runner._run_scenario(GS022_SCENARIO, rng_seed=12345)

    out = {
        "suite_version": "0.1",
        "scenario_reports": [asdict(report)],
    }
    jsonschema.validate(instance=out, schema=schema)

    assert report.passed, f"GS-022 failed: {report.failures}"
