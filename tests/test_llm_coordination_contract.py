"""
Tests for typed CoordinationProposal contract: schema validation,
allowed_actions, strict reason_code, canonical_json, and log entry.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from labtrust_gym.baselines.coordination.llm_contract import (
    Proposal,
    canonical_json,
    proposal_from_dict,
    validate_proposal,
)
from labtrust_gym.logging.episode_log import (
    EpisodeLogger,
    build_llm_coord_proposal_entry,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _valid_proposal_dict() -> dict:
    """Minimal valid proposal matching coordination_proposal.v0.1 schema."""
    return {
        "proposal_id": "prop-001",
        "step_id": 0,
        "method_id": "llm_constrained",
        "horizon_steps": 1,
        "per_agent": [
            {
                "agent_id": "worker_0",
                "action_type": "NOOP",
                "args": {},
                "reason_code": "LLM_INVALID_SCHEMA",
            },
        ],
        "comms": [
            {
                "from_agent_id": "worker_0",
                "channel": "control",
                "payload_typed": {},
                "intent": "sync",
                "ttl_steps": 1,
            },
        ],
        "meta": {
            "backend_id": "deterministic",
            "model_id": "n/a",
            "latency_ms": 0.5,
            "tokens_in": 10,
            "tokens_out": 2,
        },
    }


def test_valid_proposal_passes() -> None:
    """Proposal matching schema and allowed_actions passes validation."""
    proposal = _valid_proposal_dict()
    valid, errors = validate_proposal(
        proposal,
        allowed_actions=["NOOP", "TICK", "QUEUE_RUN"],
    )
    assert valid, errors
    assert not errors


def test_valid_proposal_passes_without_allowed_actions() -> None:
    """Schema-valid proposal passes when allowed_actions not provided."""
    proposal = _valid_proposal_dict()
    valid, errors = validate_proposal(proposal)
    assert valid, errors


def test_invalid_schema_fails_loudly() -> None:
    """Missing required fields or wrong types fail with clear errors."""
    # Missing required: proposal_id, step_id, method_id, per_agent, comms, meta
    valid, errors = validate_proposal({})
    assert not valid
    assert len(errors) >= 1
    assert any("proposal_id" in e or "required" in e.lower() for e in errors)

    # Wrong type for step_id
    proposal = _valid_proposal_dict()
    proposal["step_id"] = "not_an_int"
    valid, errors = validate_proposal(proposal)
    assert not valid
    assert len(errors) >= 1

    # per_agent item missing reason_code
    proposal = _valid_proposal_dict()
    proposal["per_agent"][0].pop("reason_code")
    valid, errors = validate_proposal(proposal)
    assert not valid
    assert len(errors) >= 1


def test_unknown_action_type_fails() -> None:
    """When allowed_actions is provided, unknown action_type fails."""
    proposal = _valid_proposal_dict()
    proposal["per_agent"][0]["action_type"] = "INVALID_ACTION_TYPE"
    valid, errors = validate_proposal(
        proposal,
        allowed_actions=["NOOP", "TICK"],
    )
    assert not valid
    assert any("not in allowed_actions" in e for e in errors)


def test_missing_reason_code_fails_when_strict() -> None:
    """When strict_reason_codes is True, missing reason_code fails."""
    registry = {"LLM_INVALID_SCHEMA": {"code": "LLM_INVALID_SCHEMA"}}
    proposal = _valid_proposal_dict()
    proposal["per_agent"][0]["reason_code"] = ""
    valid, errors = validate_proposal(
        proposal,
        strict_reason_codes=True,
        reason_code_registry=registry,
    )
    assert not valid
    assert any("reason_code" in e and "required" in e for e in errors)


def test_unknown_reason_code_fails_when_strict() -> None:
    """When strict_reason_codes is True, reason_code not in registry fails."""
    registry = {"LLM_INVALID_SCHEMA": {"code": "LLM_INVALID_SCHEMA"}}
    proposal = _valid_proposal_dict()
    proposal["per_agent"][0]["reason_code"] = "UNKNOWN_CODE"
    valid, errors = validate_proposal(
        proposal,
        strict_reason_codes=True,
        reason_code_registry=registry,
    )
    assert not valid
    assert any("not in reason_code_registry" in e for e in errors)


def test_strict_reason_codes_valid_passes() -> None:
    """When strict_reason_codes is True and reason_code in registry, passes."""
    registry = {"LLM_INVALID_SCHEMA": {"code": "LLM_INVALID_SCHEMA"}}
    proposal = _valid_proposal_dict()
    valid, errors = validate_proposal(
        proposal,
        strict_reason_codes=True,
        reason_code_registry=registry,
    )
    assert valid, errors


def test_canonical_json_deterministic() -> None:
    """canonical_json produces same string for same content (for hashing)."""
    proposal = _valid_proposal_dict()
    a = canonical_json(proposal)
    b = canonical_json(proposal)
    assert a == b
    # Parses back
    parsed = json.loads(a)
    assert parsed["proposal_id"] == proposal["proposal_id"]
    assert parsed["step_id"] == proposal["step_id"]


def test_proposal_from_dict() -> None:
    """proposal_from_dict builds Proposal dataclass from validated dict."""
    proposal = _valid_proposal_dict()
    p = proposal_from_dict(proposal)
    assert isinstance(p, Proposal)
    assert p.proposal_id == "prop-001"
    assert p.step_id == 0
    assert p.method_id == "llm_constrained"
    assert len(p.per_agent) == 1
    assert p.per_agent[0].agent_id == "worker_0"
    assert p.per_agent[0].action_type == "NOOP"
    assert p.per_agent[0].reason_code == "LLM_INVALID_SCHEMA"
    assert len(p.comms) == 1
    assert p.comms[0].from_agent_id == "worker_0"
    assert p.meta.backend_id == "deterministic"
    assert p.meta.tokens_in == 10


def test_build_llm_coord_proposal_entry() -> None:
    """build_llm_coord_proposal_entry produces log_type LLM_COORD_PROPOSAL."""
    entry = build_llm_coord_proposal_entry(
        proposal_id="p1",
        step_id=1,
        canonical_proposal_hash="sha256:abc",
        meta={"backend_id": "test", "latency_ms": 1.0},
        shield_outcomes={"blocked": False},
    )
    assert entry["log_type"] == "LLM_COORD_PROPOSAL"
    assert entry["proposal_id"] == "p1"
    assert entry["step_id"] == 1
    assert entry["canonical_proposal_hash"] == "sha256:abc"
    assert entry["meta"]["backend_id"] == "test"
    assert entry["shield_outcomes"]["blocked"] is False


def test_episode_logger_log_llm_coord_proposal() -> None:
    """EpisodeLogger.log_llm_coord_proposal writes one JSONL line."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "episode.jsonl"
        logger = EpisodeLogger(path=path)
        record = build_llm_coord_proposal_entry(
            proposal_id="p1",
            step_id=0,
            canonical_proposal_hash="h1",
            meta={},
        )
        logger.log_llm_coord_proposal(record)
        logger.close()
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["log_type"] == "LLM_COORD_PROPOSAL"
        assert data["proposal_id"] == "p1"


def test_unknown_top_level_key_fails_with_strict_schema() -> None:
    """Schema has additionalProperties: false; unknown top-level key fails."""
    proposal = _valid_proposal_dict()
    proposal["unknown_key"] = "value"
    valid, errors = validate_proposal(proposal)
    assert not valid
    assert any("additional" in e.lower() or "unknown" in e.lower() for e in errors)


def test_args_must_be_object() -> None:
    """per_agent[].args must be object (schema and contract enforce)."""
    proposal = _valid_proposal_dict()
    proposal["per_agent"][0]["args"] = "not_an_object"
    valid, errors = validate_proposal(proposal)
    assert not valid
    assert len(errors) >= 1
