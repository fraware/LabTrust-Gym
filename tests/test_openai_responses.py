"""
OpenAI Responses API backend: schema mapping, RC_LLM_INVALID_OUTPUT, healthcheck.

- Unit tests only; no live API calls. Pipeline gating and invalid-output handling.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from labtrust_gym.baselines.llm.backends.openai_responses import (
    RC_LLM_INVALID_OUTPUT,
    SINGLE_STEP_DECISION_SCHEMA,
    SUBMIT_ACTION_TOOL,
    OpenAILiveResponsesBackend,
    _decision_to_action_proposal,
    _parse_and_validate_decision,
)
from labtrust_gym.pipeline import set_pipeline_config


def test_single_step_decision_schema_required_keys() -> None:
    """Schema has required keys: action, args, reason_code, confidence, explanation_short."""
    assert SINGLE_STEP_DECISION_SCHEMA.get("required") == [
        "action",
        "args",
        "reason_code",
        "confidence",
        "explanation_short",
    ]
    assert SINGLE_STEP_DECISION_SCHEMA.get("additionalProperties") is False


def test_decision_to_action_proposal_mapping() -> None:
    """Map single-step decision to ActionProposal (action_type, token_refs, rationale)."""
    decision = {
        "action": "NOOP",
        "args": {},
        "reason_code": None,
        "confidence": 1.0,
        "explanation_short": "No work pending.",
    }
    out = _decision_to_action_proposal(decision)
    assert out["action_type"] == "NOOP"
    assert out["args"] == {}
    assert out["reason_code"] is None
    assert out["token_refs"] == []
    assert out["rationale"] == "No work pending."
    assert out["confidence"] == 1.0
    assert out["safety_notes"] == "No work pending."


def test_responses_backend_deterministic_mode_blocks_network() -> None:
    """With pipeline_mode=deterministic, propose_action raises before any HTTP."""
    set_pipeline_config(pipeline_mode="deterministic", allow_network=False)
    backend = OpenAILiveResponsesBackend(api_key="sk-test")
    with pytest.raises(RuntimeError) as exc_info:
        backend.propose_action(
            {
                "state_summary": {},
                "allowed_actions": [{"action_type": "NOOP", "args": {}}],
            }
        )
    assert "Network is not allowed" in str(exc_info.value)


def test_responses_backend_invalid_json_returns_noop_with_reason_code() -> None:
    """When _call_api would return invalid JSON, backend returns NOOP with RC_LLM_INVALID_OUTPUT."""
    set_pipeline_config(pipeline_mode="llm_live", allow_network=True)
    backend = OpenAILiveResponsesBackend(api_key="sk-test")
    with patch.object(
        backend,
        "_call_api",
        return_value=(
            "not valid json {{{",
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        ),
    ):
        out = backend.propose_action(
            {
                "state_summary": {},
                "allowed_actions": [{"action_type": "NOOP", "args": {}}],
            }
        )
    assert out["action_type"] == "NOOP"
    assert out["reason_code"] == RC_LLM_INVALID_OUTPUT
    assert "valid JSON" in (out.get("rationale") or "")


def test_responses_backend_invalid_schema_confidence_returns_noop() -> None:
    """When response has confidence outside [0,1], return NOOP with RC_LLM_INVALID_OUTPUT."""
    set_pipeline_config(pipeline_mode="llm_live", allow_network=True)
    backend = OpenAILiveResponsesBackend(api_key="sk-test")
    bad = {
        "action": "NOOP",
        "args": {},
        "reason_code": None,
        "confidence": 1.5,
        "explanation_short": "OK",
    }
    with patch.object(
        backend,
        "_call_api",
        return_value=(
            json.dumps(bad),
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        ),
    ):
        out = backend.propose_action(
            {
                "state_summary": {},
                "allowed_actions": [{"action_type": "NOOP", "args": {}}],
            }
        )
    assert out["action_type"] == "NOOP"
    assert out["reason_code"] == RC_LLM_INVALID_OUTPUT


def test_responses_backend_valid_schema_returns_action_proposal() -> None:
    """Valid schema response is mapped to ActionProposal."""
    set_pipeline_config(pipeline_mode="llm_live", allow_network=True)
    backend = OpenAILiveResponsesBackend(api_key="sk-test")
    good = {
        "action": "TICK",
        "args": {},
        "reason_code": None,
        "confidence": 0.9,
        "explanation_short": "Advance time.",
    }
    with patch.object(
        backend,
        "_call_api",
        return_value=(
            json.dumps(good),
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        ),
    ):
        out = backend.propose_action(
            {
                "state_summary": {},
                "allowed_actions": [{"action_type": "TICK", "args": {}}],
            }
        )
    assert out["action_type"] == "TICK"
    assert out["rationale"] == "Advance time."
    assert out["confidence"] == 0.9
    assert out.get("reason_code") is None


def test_healthcheck_requires_network() -> None:
    """healthcheck() calls check_network_allowed(); with deterministic it raises."""
    set_pipeline_config(pipeline_mode="deterministic", allow_network=False)
    backend = OpenAILiveResponsesBackend(api_key="sk-test")
    with pytest.raises(RuntimeError) as exc_info:
        backend.healthcheck()
    assert "Network is not allowed" in str(exc_info.value)


def test_healthcheck_no_key_returns_ok_false() -> None:
    """With no API key (or openai not installed), healthcheck returns ok=False and error message."""
    set_pipeline_config(pipeline_mode="llm_live", allow_network=True)
    backend = OpenAILiveResponsesBackend(api_key="")
    result = backend.healthcheck()
    assert result["ok"] is False
    err = result.get("error") or ""
    assert "OPENAI_API_KEY" in err or "openai not installed" in err


def test_submit_action_tool_definition() -> None:
    """submit_action tool has correct name and parameters schema."""
    assert SUBMIT_ACTION_TOOL["type"] == "function"
    assert SUBMIT_ACTION_TOOL["function"]["name"] == "submit_action"
    assert SUBMIT_ACTION_TOOL["function"]["parameters"] == SINGLE_STEP_DECISION_SCHEMA


def test_parse_and_validate_decision_valid() -> None:
    """_parse_and_validate_decision accepts valid decision JSON."""
    raw = json.dumps(
        {
            "action": "TICK",
            "args": {},
            "reason_code": "RC_OK",
            "confidence": 0.95,
            "explanation_short": "Advance clock.",
        }
    )
    decision, err = _parse_and_validate_decision(raw)
    assert err is None
    assert decision is not None
    assert decision["action"] == "TICK"
    assert decision["confidence"] == 0.95


def test_parse_and_validate_decision_invalid_json() -> None:
    """_parse_and_validate_decision returns error for invalid JSON."""
    decision, err = _parse_and_validate_decision("not json")
    assert decision is None
    assert err is not None
    assert "JSON" in err


def test_parse_and_validate_decision_invalid_confidence() -> None:
    """_parse_and_validate_decision rejects confidence outside [0,1]."""
    raw = json.dumps(
        {
            "action": "NOOP",
            "args": {},
            "reason_code": None,
            "confidence": 1.5,
            "explanation_short": "x",
        }
    )
    decision, err = _parse_and_validate_decision(raw)
    assert decision is None
    assert err is not None
    assert "confidence" in err.lower() or "range" in err.lower()


def test_json_schema_and_tool_call_produce_identical_decision() -> None:
    """Same valid decision via json_schema vs tool_call yields identical ActionProposal."""
    set_pipeline_config(pipeline_mode="llm_live", allow_network=True)
    decision = {
        "action": "PICK_SPECIMEN",
        "args": {"specimen_id": "S1"},
        "reason_code": "RC_OK",
        "confidence": 0.88,
        "explanation_short": "Pick specimen S1 for processing.",
    }
    raw = json.dumps(decision)
    usage = {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18}

    backend_json = OpenAILiveResponsesBackend(api_key="sk-test", output_mode="json_schema")
    with patch.object(backend_json, "_call_api", return_value=(raw, usage)):
        out_json = backend_json.propose_action(
            {
                "state_summary": {},
                "allowed_actions": [{"action_type": "PICK_SPECIMEN", "args": {}}],
            }
        )

    backend_tool = OpenAILiveResponsesBackend(api_key="sk-test", output_mode="tool_call")
    with patch.object(backend_tool, "_call_api_tool_call", return_value=(raw, usage)):
        out_tool = backend_tool.propose_action(
            {
                "state_summary": {},
                "allowed_actions": [{"action_type": "PICK_SPECIMEN", "args": {}}],
            }
        )

    expected = _decision_to_action_proposal(decision)
    assert out_json == expected
    assert out_tool == expected
    assert out_json == out_tool


def test_tool_call_path_valid_arguments_returns_action_proposal() -> None:
    """Tool-call path: valid submit_action arguments produce correct ActionProposal."""
    set_pipeline_config(pipeline_mode="llm_live", allow_network=True)
    backend = OpenAILiveResponsesBackend(api_key="sk-test", output_mode="tool_call")
    decision = {
        "action": "NOOP",
        "args": {},
        "reason_code": None,
        "confidence": 1.0,
        "explanation_short": "Nothing to do.",
    }
    with patch.object(
        backend,
        "_call_api_tool_call",
        return_value=(
            json.dumps(decision),
            {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        ),
    ):
        out = backend.propose_action(
            {
                "state_summary": {},
                "allowed_actions": [{"action_type": "NOOP", "args": {}}],
            }
        )
    assert out["action_type"] == "NOOP"
    assert out["rationale"] == "Nothing to do."
    assert out["confidence"] == 1.0
    assert out == _decision_to_action_proposal(decision)


def test_tool_call_path_invalid_arguments_returns_noop() -> None:
    """Tool-call path: invalid JSON in arguments returns NOOP with RC_LLM_INVALID_OUTPUT."""
    set_pipeline_config(pipeline_mode="llm_live", allow_network=True)
    backend = OpenAILiveResponsesBackend(api_key="sk-test", output_mode="tool_call")
    with patch.object(
        backend,
        "_call_api_tool_call",
        return_value=(
            "{ invalid }",
            {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        ),
    ):
        out = backend.propose_action(
            {
                "state_summary": {},
                "allowed_actions": [{"action_type": "NOOP", "args": {}}],
            }
        )
    assert out["action_type"] == "NOOP"
    assert out["reason_code"] == RC_LLM_INVALID_OUTPUT
    assert "JSON" in (out.get("rationale") or "")


def test_tool_call_path_invalid_schema_returns_noop() -> None:
    """Tool-call path: valid JSON but invalid schema (e.g. confidence 1.5) returns NOOP."""
    set_pipeline_config(pipeline_mode="llm_live", allow_network=True)
    backend = OpenAILiveResponsesBackend(api_key="sk-test", output_mode="tool_call")
    bad = {
        "action": "TICK",
        "args": {},
        "reason_code": None,
        "confidence": 1.5,
        "explanation_short": "x",
    }
    with patch.object(
        backend,
        "_call_api_tool_call",
        return_value=(
            json.dumps(bad),
            {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        ),
    ):
        out = backend.propose_action(
            {
                "state_summary": {},
                "allowed_actions": [{"action_type": "TICK", "args": {}}],
            }
        )
    assert out["action_type"] == "NOOP"
    assert out["reason_code"] == RC_LLM_INVALID_OUTPUT
