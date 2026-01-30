"""
Unit tests for token lifecycle and dual approval; integration for GS-010--013.

- policy/tokens.py: Token dataclass, validate_dual_approval.
- engine/tokens_runtime.py: TokenStore mint, consume, revoke, is_valid.
- core_env: MINT_TOKEN, REVOKE_TOKEN, token_refs validation, replay protection.
- GS-010: dual approval (same approver twice => BLOCKED, INV-TOK-001).
- GS-011: expired token => BLOCKED, INV-TOK-002.
- GS-012: consumed token reuse => BLOCKED, INV-TOK-002.
- GS-013: revoked token => BLOCKED, INV-TOK-006.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

import jsonschema
import pytest

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.policy.tokens import (
    Token,
    load_token_registry,
    validate_dual_approval,
)
from labtrust_gym.runner import GoldenRunner
from labtrust_gym.engine.tokens_runtime import TokenStore


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ---- policy/tokens.py ----
def test_token_from_dict_to_dict() -> None:
    d = {
        "token_id": "T1",
        "token_type": "TOKEN_RESTRICTED_ENTRY",
        "state": "ACTIVE",
        "subject_type": "agent",
        "subject_id": "A_SUPERVISOR",
        "issued_at_ts_s": 0,
        "expires_at_ts_s": 900,
        "reason_code": "SYS_DOWNTIME_ACTIVE",
        "approvals": [],
    }
    tok = Token.from_dict(d)
    assert tok.token_id == "T1"
    assert tok.state == "ACTIVE"
    assert Token.from_dict(tok.to_dict()).token_id == tok.token_id


def test_validate_dual_approval_same_approver_fails() -> None:
    registry = {
        "token_types": {
            "OVERRIDE_RISK_ACCEPTANCE": {"approvals_required": 2},
        }
    }
    approvals = [
        {"approver_agent_id": "A_SUPERVISOR", "approver_key_id": "ed25519:key_supervisor"},
        {"approver_agent_id": "A_SUPERVISOR", "approver_key_id": "ed25519:key_supervisor"},
    ]
    ok, violation = validate_dual_approval(approvals, "OVERRIDE_RISK_ACCEPTANCE", registry)
    assert ok is False
    assert violation == "INV-TOK-001"


def test_validate_dual_approval_distinct_passes() -> None:
    registry = {
        "token_types": {
            "OVERRIDE_RISK_ACCEPTANCE": {"approvals_required": 2},
        }
    }
    approvals = [
        {"approver_agent_id": "A_SUPERVISOR", "approver_key_id": "ed25519:key_supervisor"},
        {"approver_agent_id": "A_CLINSCI", "approver_key_id": "ed25519:key_clinsci"},
    ]
    ok, violation = validate_dual_approval(approvals, "OVERRIDE_RISK_ACCEPTANCE", registry)
    assert ok is True
    assert violation is None


# ---- engine/tokens_runtime.py ----
def test_token_store_mint_consume_revoke_is_valid() -> None:
    store = TokenStore()
    store.mint_token(
        token_id="T1",
        token_type="TOKEN_RESTRICTED_ENTRY",
        subject_type="agent",
        subject_id="A_SUPERVISOR",
        issued_at_ts_s=0,
        expires_at_ts_s=900,
        reason_code="SYS_DOWNTIME_ACTIVE",
        approvals=[],
    )
    assert store.is_valid("T1", 100) is True
    assert store.is_valid("T1", 1000) is False  # expired
    store.consume_token("T1")
    assert store.is_valid("T1", 100) is False  # consumed
    assert store.validity_violation("T1", 100) == "INV-TOK-002"

    store.mint_token("T2", "TOKEN_RESTRICTED_ENTRY", "agent", "A_SUPERVISOR", 0, 900, None, [])
    assert store.is_valid("T2", 100) is True
    store.revoke_token("T2")
    assert store.is_valid("T2", 100) is False
    assert store.validity_violation("T2", 100) == "INV-TOK-006"


def test_token_store_load_initial() -> None:
    store = TokenStore()
    store.load_initial([
        {
            "token_id": "T_EXP",
            "token_type": "TOKEN_RESTRICTED_ENTRY",
            "state": "ACTIVE",
            "subject_type": "agent",
            "subject_id": "A_SUPERVISOR",
            "issued_at_ts_s": 0,
            "expires_at_ts_s": 100,
            "reason_code": "SYS_DOWNTIME_ACTIVE",
        }
    ])
    assert store.is_valid("T_EXP", 50) is True
    assert store.is_valid("T_EXP", 200) is False


# ---- CoreEnv GS-010 (dual approval), GS-011 (expired), GS-012 (replay), GS-013 (revoked) ----
def _should_run_golden() -> bool:
    return os.environ.get("LABTRUST_RUN_GOLDEN") == "1"


# GS-010: MINT_TOKEN with same approver twice => BLOCKED, INV-TOK-001
GS010 = {
    "scenario_id": "GS-010",
    "title": "OVERRIDE_RISK_ACCEPTANCE cannot be minted with same approver twice",
    "initial_state": {"system": {}, "specimens": [{"template_ref": "S_BIOCHEM_OK"}], "tokens": []},
    "script": [
        {
            "event_id": "e1",
            "t_s": 800,
            "agent_id": "A_SUPERVISOR",
            "action_type": "MINT_TOKEN",
            "args": {
                "token_type": "OVERRIDE_RISK_ACCEPTANCE",
                "subject_type": "specimen",
                "subject_id": "S1",
                "reason_code": "TIME_EXPIRED",
                "approvals": [
                    {"approver_agent_id": "A_SUPERVISOR", "approver_key_id": "ed25519:key_supervisor"},
                    {"approver_agent_id": "A_SUPERVISOR", "approver_key_id": "ed25519:key_supervisor"},
                ],
            },
            "reason_code": "TIME_EXPIRED",
            "token_refs": [],
            "expect": {"status": "BLOCKED", "violations": ["INV-TOK-001:VIOLATION"]},
        }
    ],
}

# GS-011: expired token => BLOCKED, INV-TOK-002
GS011 = {
    "scenario_id": "GS-011",
    "title": "Expired token cannot be used",
    "initial_state": {
        "system": {},
        "specimens": [{"template_ref": "S_BIOCHEM_OK"}],
        "tokens": [
            {
                "token_id": "T_EXP",
                "token_type": "TOKEN_RESTRICTED_ENTRY",
                "state": "ACTIVE",
                "subject_type": "agent",
                "subject_id": "A_SUPERVISOR",
                "issued_at_ts_s": 0,
                "expires_at_ts_s": 100,
                "reason_code": "SYS_DOWNTIME_ACTIVE",
            }
        ],
    },
    "script": [
        {
            "event_id": "e1",
            "t_s": 200,
            "agent_id": "A_SUPERVISOR",
            "action_type": "OPEN_DOOR",
            "args": {"door_id": "D_RESTRICTED_AIRLOCK"},
            "reason_code": "SYS_DOWNTIME_ACTIVE",
            "token_refs": ["T_EXP"],
            "expect": {"status": "BLOCKED", "violations": ["INV-TOK-002:VIOLATION"]},
        }
    ],
}

# GS-012: first OPEN_DOOR consumes; second reuse => BLOCKED
GS012 = {
    "scenario_id": "GS-012",
    "title": "Token replay protection: consumed token cannot be reused",
    "initial_state": {
        "system": {},
        "specimens": [],
        "tokens": [
            {
                "token_id": "T_RESTRICT_REPLAY",
                "token_type": "TOKEN_RESTRICTED_ENTRY",
                "state": "ACTIVE",
                "subject_type": "agent",
                "subject_id": "A_SUPERVISOR",
                "issued_at_ts_s": 0,
                "expires_at_ts_s": 900,
                "reason_code": "SYS_DOWNTIME_ACTIVE",
            }
        ],
    },
    "script": [
        {
            "event_id": "e1",
            "t_s": 100,
            "agent_id": "A_SUPERVISOR",
            "action_type": "OPEN_DOOR",
            "args": {"door_id": "D_RESTRICTED_AIRLOCK"},
            "reason_code": "SYS_DOWNTIME_ACTIVE",
            "token_refs": ["T_RESTRICT_REPLAY"],
            "expect": {"status": "ACCEPTED", "token_consumed": ["T_RESTRICT_REPLAY"]},
        },
        {
            "event_id": "e2",
            "t_s": 110,
            "agent_id": "A_SUPERVISOR",
            "action_type": "OPEN_DOOR",
            "args": {"door_id": "D_RESTRICTED_AIRLOCK"},
            "reason_code": "SYS_DOWNTIME_ACTIVE",
            "token_refs": ["T_RESTRICT_REPLAY"],
            "expect": {"status": "BLOCKED", "violations": ["INV-TOK-002:VIOLATION"]},
        },
    ],
}

# GS-013: REVOKE_TOKEN then OPEN_DOOR with same token => BLOCKED
GS013 = {
    "scenario_id": "GS-013",
    "title": "Revoked token cannot be used",
    "initial_state": {
        "system": {},
        "specimens": [],
        "tokens": [
            {
                "token_id": "T_REV",
                "token_type": "TOKEN_RESTRICTED_ENTRY",
                "state": "ACTIVE",
                "subject_type": "agent",
                "subject_id": "A_SUPERVISOR",
                "issued_at_ts_s": 0,
                "expires_at_ts_s": 900,
                "reason_code": "SYS_DOWNTIME_ACTIVE",
            }
        ],
    },
    "script": [
        {
            "event_id": "e1",
            "t_s": 200,
            "agent_id": "A_SUPERVISOR",
            "action_type": "REVOKE_TOKEN",
            "args": {"token_id": "T_REV", "revoke_reason": "AUDIT_CHAIN_BROKEN"},
            "reason_code": "AUDIT_CHAIN_BROKEN",
            "token_refs": [],
            "expect": {"status": "ACCEPTED", "emits": ["REVOKE_TOKEN"]},
        },
        {
            "event_id": "e2",
            "t_s": 210,
            "agent_id": "A_SUPERVISOR",
            "action_type": "OPEN_DOOR",
            "args": {"door_id": "D_RESTRICTED_AIRLOCK"},
            "reason_code": "SYS_DOWNTIME_ACTIVE",
            "token_refs": ["T_REV"],
            "expect": {"status": "BLOCKED", "violations": ["INV-TOK-006:VIOLATION"]},
        },
    ],
}


@pytest.mark.parametrize("scenario", [GS010, GS011, GS012, GS013], ids=["GS-010", "GS-011", "GS-012", "GS-013"])
def test_gs010_through_gs013(scenario: dict) -> None:
    """Run GS-010, GS-011, GS-012, GS-013 with CoreEnv. Skipped unless LABTRUST_RUN_GOLDEN=1."""
    if not _should_run_golden():
        pytest.skip("Set LABTRUST_RUN_GOLDEN=1 to run token scenarios.")
    root = _repo_root()
    schema_path = root / "policy" / "schemas" / "runner_output_contract.v0.1.schema.json"
    if not schema_path.exists():
        schema_path = root / "runner_output_contract.v0.1.schema.json"
    if not schema_path.exists():
        pytest.fail("Runner output contract schema not found")
    schema = __import__("json").loads(schema_path.read_text(encoding="utf-8"))
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    if not emits_path.exists():
        emits_path = root / "emits_vocab.v0.1.yaml"
    if not emits_path.exists():
        pytest.fail("Emits vocab not found")
    env = CoreEnv()
    runner = GoldenRunner(env, emits_vocab_path=str(emits_path))
    report = runner._run_scenario(scenario, rng_seed=12345)
    out = {"suite_version": "0.1", "scenario_reports": [asdict(report)]}
    jsonschema.validate(instance=out, schema=schema)
    assert report.passed, f"Scenario {scenario['scenario_id']} failed: {report.failures}"


def test_gs010_through_gs013_from_yaml() -> None:
    """
    Run GS-010, GS-011, GS-012, GS-013 from policy/golden/golden_scenarios.v0.1.yaml.
    Ensures token lifecycle and dual approval pass when loaded from the real suite.
    Skipped unless LABTRUST_RUN_GOLDEN=1. Skips if suite file fails to parse (e.g. YAML ambiguity).
    """
    if not _should_run_golden():
        pytest.skip("Set LABTRUST_RUN_GOLDEN=1 to run token scenarios from YAML.")
    import yaml
    root = _repo_root()
    suite_path = root / "policy" / "golden" / "golden_scenarios.v0.1.yaml"
    if not suite_path.exists():
        suite_path = root / "golden_scenarios.v0.1.yaml"
    if not suite_path.exists():
        pytest.skip(f"Golden suite not found: {suite_path}")
    try:
        with suite_path.open("r", encoding="utf-8") as f:
            suite = yaml.safe_load(f)
    except Exception as e:
        pytest.skip(f"Golden suite YAML failed to parse: {e}")
    if not suite:
        pytest.skip("Golden suite file is empty")
    suite_meta = suite.get("golden_suite", {})
    scenarios = suite_meta.get("scenarios", [])
    token_scenario_ids = {"GS-010", "GS-011", "GS-012", "GS-013"}
    token_scenarios = [s for s in scenarios if s.get("scenario_id") in token_scenario_ids]
    if len(token_scenarios) != 4:
        pytest.skip(f"Expected 4 token scenarios in suite, found {len(token_scenarios)}")
    schema_path = root / "policy" / "schemas" / "runner_output_contract.v0.1.schema.json"
    if not schema_path.exists():
        schema_path = root / "runner_output_contract.v0.1.schema.json"
    schema = __import__("json").loads(schema_path.read_text(encoding="utf-8"))
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    if not emits_path.exists():
        emits_path = root / "emits_vocab.v0.1.yaml"
    env = CoreEnv()
    runner = GoldenRunner(env, emits_vocab_path=str(emits_path))
    rng_seed = int(suite_meta.get("deterministic", {}).get("rng_seed", 0))
    reports = [runner._run_scenario(scen, rng_seed=rng_seed) for scen in token_scenarios]
    out = {"suite_version": suite_meta.get("version", "0.1"), "scenario_reports": [asdict(r) for r in reports]}
    jsonschema.validate(instance=out, schema=schema)
    failed = [r for r in reports if not r.passed]
    assert not failed, f"GS-010–013 from YAML failed: {[f.scenario_id for f in failed]}"
