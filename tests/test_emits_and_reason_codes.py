"""
Tests for strict validation of emits and reason codes.

- policy/emits.py: load allowed emits, validate engine outputs (unknown => AssertionError).
- policy/reason_codes.py: load registry, lookup, validate (unknown => AssertionError).
- GoldenRunner: non-strict (any reason code allowed); strict (LABTRUST_STRICT_REASON_CODES=1)
  enforces blocked_reason_code and action reason_code must be in registry.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from labtrust_gym.policy.emits import (
    load_emits_vocab,
    validate_emits,
    validate_engine_step_emits,
)
from labtrust_gym.policy.reason_codes import (
    allowed_codes,
    get_code,
    load_reason_code_registry,
    validate_reason_code,
)
from labtrust_gym.runner import GoldenRunner, LabTrustEnvAdapter


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ---- policy/emits.py ----
def test_load_emits_vocab_returns_set() -> None:
    root = _repo_root()
    path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    if not path.exists():
        path = root / "emits_vocab.v0.1.yaml"
    if not path.exists():
        pytest.skip("Emits vocab not found")
    allowed = load_emits_vocab(path)
    assert isinstance(allowed, set)
    assert "CREATE_ACCESSION" in allowed
    assert "FORENSIC_FREEZE_LOG" in allowed


def test_validate_emits_accepts_allowed() -> None:
    allowed = {"A", "B", "C"}
    validate_emits(["A", "B"], allowed, event_id="e1")
    validate_emits([], allowed, event_id="e1")


def test_validate_emits_raises_on_unknown() -> None:
    allowed = {"A", "B"}
    with pytest.raises(AssertionError, match="unknown emits"):
        validate_emits(["A", "X"], allowed, event_id="e1")


def test_validate_engine_step_emits() -> None:
    allowed = {"CREATE_ACCESSION"}
    validate_engine_step_emits({"emits": ["CREATE_ACCESSION"]}, allowed, event_id="e1")
    with pytest.raises(AssertionError, match="unknown emits"):
        validate_engine_step_emits({"emits": ["UNKNOWN"]}, allowed, event_id="e1")


# ---- policy/reason_codes.py ----
def test_load_reason_code_registry() -> None:
    root = _repo_root()
    path = root / "policy" / "reason_codes" / "reason_code_registry.v0.1.yaml"
    if not path.exists():
        path = root / "reason_code_registry.v0.1.yaml"
    if not path.exists():
        pytest.skip("Reason code registry not found")
    reg = load_reason_code_registry(path)
    assert isinstance(reg, dict)
    assert "AUDIT_CHAIN_BROKEN" in reg
    assert "AUDIT_MISSING_REASON_CODE" in reg
    assert "RC_DEVICE_NOT_COLOCATED" in reg


def test_get_code_and_allowed_codes() -> None:
    root = _repo_root()
    path = root / "policy" / "reason_codes" / "reason_code_registry.v0.1.yaml"
    if not path.exists():
        pytest.skip("Reason code registry not found")
    reg = load_reason_code_registry(path)
    info = get_code(reg, "AUDIT_CHAIN_BROKEN")
    assert info is not None
    assert info.get("namespace") == "AUD"
    assert "AUDIT_CHAIN_BROKEN" in allowed_codes(reg)


def test_validate_reason_code_accepts_registered() -> None:
    reg = {"AUDIT_CHAIN_BROKEN": {"code": "AUDIT_CHAIN_BROKEN", "namespace": "AUD"}}
    validate_reason_code("AUDIT_CHAIN_BROKEN", reg, event_id="e1")
    validate_reason_code(None, reg, event_id="e1")


def test_validate_reason_code_raises_on_unknown() -> None:
    reg = {"AUDIT_CHAIN_BROKEN": {}}
    with pytest.raises(AssertionError, match="unknown.*reason_code"):
        validate_reason_code("UNKNOWN_CODE", reg, event_id="e1", context="reason_code")


# ---- GoldenRunner strict vs non-strict ----
class _MockEnv(LabTrustEnvAdapter):
    """Returns fixed step result for testing."""

    def __init__(self, step_result: dict):
        self.step_result = step_result

    def reset(self, initial_state, *, deterministic: bool, rng_seed: int) -> None:
        pass

    def step(self, event):
        return self.step_result

    def query(self, expr: str):
        return None


def test_golden_runner_non_strict_accepts_any_reason_code() -> None:
    """Without LABTRUST_STRICT_REASON_CODES, unknown reason codes are allowed."""
    prev = os.environ.pop("LABTRUST_STRICT_REASON_CODES", None)
    try:
        root = _repo_root()
        emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
        if not emits_path.exists():
            emits_path = root / "emits_vocab.v0.1.yaml"
        if not emits_path.exists():
            pytest.skip("Emits vocab not found")
        env = _MockEnv({
            "status": "BLOCKED",
            "emits": [],
            "violations": [],
            "blocked_reason_code": "SOME_UNKNOWN_CODE",
            "token_consumed": [],
            "hashchain": {"head_hash": "x", "length": 0, "last_event_hash": "x"},
        })
        runner = GoldenRunner(env, emits_vocab_path=str(emits_path), strict_reason_codes=False)
        step = {"event_id": "e1", "t_s": 0, "agent_id": "A", "action_type": "X", "args": {}, "reason_code": None, "token_refs": []}
        report = runner._run_step(step)
        assert report.status == "BLOCKED"
        assert report.blocked_reason_code == "SOME_UNKNOWN_CODE"
    finally:
        if prev is not None:
            os.environ["LABTRUST_STRICT_REASON_CODES"] = prev


def test_golden_runner_strict_rejects_unknown_blocked_reason_code() -> None:
    """With strict reason codes, unknown blocked_reason_code raises AssertionError."""
    root = _repo_root()
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    reason_path = root / "policy" / "reason_codes" / "reason_code_registry.v0.1.yaml"
    if not emits_path.exists():
        emits_path = root / "emits_vocab.v0.1.yaml"
    if not reason_path.exists():
        reason_path = root / "reason_code_registry.v0.1.yaml"
    if not emits_path.exists() or not reason_path.exists():
        pytest.skip("Policy files not found")
    env = _MockEnv({
        "status": "BLOCKED",
        "emits": [],
        "violations": [],
        "blocked_reason_code": "NOT_IN_REGISTRY_CODE",
        "token_consumed": [],
        "hashchain": {"head_hash": "x", "length": 0, "last_event_hash": "x"},
    })
    runner = GoldenRunner(
        env,
        emits_vocab_path=str(emits_path),
        reason_code_registry_path=str(reason_path),
        strict_reason_codes=True,
    )
    step = {"event_id": "e1", "t_s": 0, "agent_id": "A", "action_type": "X", "args": {}, "reason_code": None, "token_refs": []}
    with pytest.raises(AssertionError, match="unknown.*blocked_reason_code|NOT_IN_REGISTRY"):
        runner._run_step(step)


def test_golden_runner_strict_accepts_registered_reason_code() -> None:
    """With strict reason codes, registered blocked_reason_code passes."""
    root = _repo_root()
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    reason_path = root / "policy" / "reason_codes" / "reason_code_registry.v0.1.yaml"
    if not emits_path.exists():
        emits_path = root / "emits_vocab.v0.1.yaml"
    if not reason_path.exists():
        reason_path = root / "reason_code_registry.v0.1.yaml"
    if not emits_path.exists() or not reason_path.exists():
        pytest.skip("Policy files not found")
    env = _MockEnv({
        "status": "BLOCKED",
        "emits": [],
        "violations": [],
        "blocked_reason_code": "AUDIT_CHAIN_BROKEN",
        "token_consumed": [],
        "hashchain": {"head_hash": "x", "length": 0, "last_event_hash": "x"},
    })
    runner = GoldenRunner(
        env,
        emits_vocab_path=str(emits_path),
        reason_code_registry_path=str(reason_path),
        strict_reason_codes=True,
    )
    step = {"event_id": "e1", "t_s": 0, "agent_id": "A", "action_type": "X", "args": {}, "reason_code": None, "token_refs": []}
    report = runner._run_step(step)
    assert report.status == "BLOCKED"
    assert report.blocked_reason_code == "AUDIT_CHAIN_BROKEN"


def test_golden_runner_strict_rejects_unknown_action_reason_code() -> None:
    """With strict reason codes, unknown event.reason_code raises AssertionError."""
    root = _repo_root()
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    reason_path = root / "policy" / "reason_codes" / "reason_code_registry.v0.1.yaml"
    if not emits_path.exists():
        emits_path = root / "emits_vocab.v0.1.yaml"
    if not reason_path.exists():
        reason_path = root / "reason_code_registry.v0.1.yaml"
    if not emits_path.exists() or not reason_path.exists():
        pytest.skip("Policy files not found")
    env = _MockEnv({
        "status": "ACCEPTED",
        "emits": ["MINT_TOKEN"],
        "violations": [],
        "blocked_reason_code": None,
        "token_consumed": [],
        "hashchain": {"head_hash": "x", "length": 1, "last_event_hash": "y"},
    })
    runner = GoldenRunner(
        env,
        emits_vocab_path=str(emits_path),
        reason_code_registry_path=str(reason_path),
        strict_reason_codes=True,
    )
    step = {"event_id": "e1", "t_s": 0, "agent_id": "A", "action_type": "MINT_TOKEN", "args": {}, "reason_code": "UNKNOWN_ACTION_CODE", "token_refs": []}
    with pytest.raises(AssertionError, match="unknown.*reason_code|UNKNOWN_ACTION"):
        runner._run_step(step)


def test_golden_runner_strict_accepts_registered_event_reason_code() -> None:
    """With strict reason codes, registered event.reason_code passes."""
    root = _repo_root()
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    reason_path = root / "policy" / "reason_codes" / "reason_code_registry.v0.1.yaml"
    if not emits_path.exists():
        emits_path = root / "emits_vocab.v0.1.yaml"
    if not reason_path.exists():
        reason_path = root / "reason_code_registry.v0.1.yaml"
    if not emits_path.exists() or not reason_path.exists():
        pytest.skip("Policy files not found")
    env = _MockEnv({
        "status": "ACCEPTED",
        "emits": ["REJECT_SPECIMEN"],
        "violations": [],
        "blocked_reason_code": None,
        "token_consumed": [],
        "hashchain": {"head_hash": "x", "length": 1, "last_event_hash": "y"},
    })
    runner = GoldenRunner(
        env,
        emits_vocab_path=str(emits_path),
        reason_code_registry_path=str(reason_path),
        strict_reason_codes=True,
    )
    step = {
        "event_id": "e1",
        "t_s": 0,
        "agent_id": "A",
        "action_type": "REJECT_SPECIMEN",
        "args": {},
        "reason_code": "RC_LABEL_MISMATCH",
        "token_refs": [],
    }
    report = runner._run_step(step)
    assert report.status == "ACCEPTED"
    assert report.blocked_reason_code is None
