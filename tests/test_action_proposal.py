"""
ActionProposal v0.1 schema validation: valid passes, missing key fails,
additionalProperties fails, NOOP requires args={}, token_refs=[], reason_code=null.
"""

from pathlib import Path

import pytest

from labtrust_gym.baselines.llm.action_proposal import (
    load_action_proposal_schema,
    validate_action_proposal_dict,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _schema_path() -> Path:
    return _repo_root() / "policy" / "schemas" / "action_proposal.v0.1.schema.json"


def _valid_non_noop() -> dict:
    return {
        "action_type": "TICK",
        "args": {},
        "reason_code": None,
        "token_refs": [],
        "rationale": "Advance time.",
        "confidence": 0.9,
        "safety_notes": "",
    }


def _valid_noop() -> dict:
    return {
        "action_type": "NOOP",
        "args": {},
        "reason_code": None,
        "token_refs": [],
        "rationale": "No action needed.",
        "confidence": 0.5,
        "safety_notes": "",
    }


def test_load_action_proposal_schema() -> None:
    """Schema loads from repo policy/schemas when path exists."""
    path = _schema_path()
    if not path.exists():
        pytest.skip("action_proposal.v0.1.schema.json not found")
    schema = load_action_proposal_schema(path)
    assert schema
    assert schema.get("$schema") == "http://json-schema.org/draft-07/schema#"
    assert "action_type" in schema.get("properties", {})


def test_validate_action_proposal_valid_passes() -> None:
    """Valid proposal (non-NOOP) passes and returns normalized dict."""
    path = _schema_path()
    if not path.exists():
        pytest.skip("action_proposal.v0.1.schema.json not found")
    schema = load_action_proposal_schema(path)
    d = _valid_non_noop()
    ok, normalized, error_reason = validate_action_proposal_dict(d, schema=schema)
    assert ok is True
    assert error_reason is None
    assert normalized is not None
    assert normalized.get("action_type") == "TICK"
    assert "rationale" in normalized
    assert "confidence" in normalized


def test_validate_action_proposal_missing_key_fails() -> None:
    """Missing required key (e.g. rationale) fails."""
    path = _schema_path()
    if not path.exists():
        pytest.skip("action_proposal.v0.1.schema.json not found")
    schema = load_action_proposal_schema(path)
    d = _valid_non_noop()
    del d["rationale"]
    ok, normalized, error_reason = validate_action_proposal_dict(d, schema=schema)
    assert ok is False
    assert normalized is None
    assert error_reason is not None
    assert "rationale" in error_reason or "required" in error_reason.lower()


def test_validate_action_proposal_additional_properties_fails() -> None:
    """Unknown key (additionalProperties: false) fails."""
    path = _schema_path()
    if not path.exists():
        pytest.skip("action_proposal.v0.1.schema.json not found")
    schema = load_action_proposal_schema(path)
    d = _valid_non_noop()
    d["foo"] = "bar"
    ok, normalized, error_reason = validate_action_proposal_dict(d, schema=schema)
    assert ok is False
    assert normalized is None
    assert error_reason is not None
    assert "foo" in error_reason or "additional" in error_reason.lower()


def test_validate_action_proposal_noop_requires_empty_args() -> None:
    """NOOP with non-empty args fails (allOf then: args maxProperties 0)."""
    path = _schema_path()
    if not path.exists():
        pytest.skip("action_proposal.v0.1.schema.json not found")
    schema = load_action_proposal_schema(path)
    d = _valid_noop()
    d["args"] = {"x": 1}
    ok, normalized, error_reason = validate_action_proposal_dict(d, schema=schema)
    assert ok is False
    assert normalized is None
    assert error_reason is not None


def test_validate_action_proposal_noop_requires_empty_token_refs() -> None:
    """NOOP with non-empty token_refs fails (allOf then: token_refs maxItems 0)."""
    path = _schema_path()
    if not path.exists():
        pytest.skip("action_proposal.v0.1.schema.json not found")
    schema = load_action_proposal_schema(path)
    d = _valid_noop()
    d["token_refs"] = ["T1"]
    ok, normalized, error_reason = validate_action_proposal_dict(d, schema=schema)
    assert ok is False
    assert normalized is None
    assert error_reason is not None


def test_validate_action_proposal_noop_requires_reason_code_null() -> None:
    """NOOP with non-null reason_code fails (allOf then: reason_code type null)."""
    path = _schema_path()
    if not path.exists():
        pytest.skip("action_proposal.v0.1.schema.json not found")
    schema = load_action_proposal_schema(path)
    d = _valid_noop()
    d["reason_code"] = "SOME_CODE"
    ok, normalized, error_reason = validate_action_proposal_dict(d, schema=schema)
    assert ok is False
    assert normalized is None
    assert error_reason is not None


def test_validate_action_proposal_valid_noop_passes() -> None:
    """Valid NOOP (args={}, token_refs=[], reason_code=null) passes."""
    path = _schema_path()
    if not path.exists():
        pytest.skip("action_proposal.v0.1.schema.json not found")
    schema = load_action_proposal_schema(path)
    d = _valid_noop()
    ok, normalized, error_reason = validate_action_proposal_dict(d, schema=schema)
    assert ok is True
    assert error_reason is None
    assert normalized is not None
    assert normalized.get("action_type") == "NOOP"
    assert normalized.get("args") == {}
    assert normalized.get("token_refs") == []
    assert normalized.get("reason_code") is None
