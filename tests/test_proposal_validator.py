"""
Unit tests for deterministic proposal validator (2-stage: propose then validate).
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.llm.proposal_validator import (
    RC_LLM_PROPOSED_INVALID,
    validate_proposal_deterministic,
)


def test_validator_action_not_in_allowed() -> None:
    """Proposal with action_type not in allowed_actions is invalid."""
    proposal = {
        "action_type": "RELEASE_RESULT",
        "args": {},
        "reason_code": None,
        "token_refs": [],
        "rationale": "x",
    }
    allowed = ["NOOP", "TICK", "CREATE_ACCESSION"]
    valid, errors = validate_proposal_deterministic(proposal, allowed)
    assert valid is False
    assert "action_type not in allowed_actions" in errors


def test_validator_action_in_allowed_noop() -> None:
    """NOOP with empty args is valid."""
    proposal = {
        "action_type": "NOOP",
        "args": {},
        "reason_code": None,
        "token_refs": [],
        "rationale": "x",
    }
    valid, errors = validate_proposal_deterministic(proposal, ["NOOP", "TICK"])
    assert valid is True
    assert len(errors) == 0


def test_validator_args_required_for_move() -> None:
    """MOVE without from_zone/to_zone is invalid."""
    proposal = {
        "action_type": "MOVE",
        "args": {},
        "reason_code": None,
        "token_refs": [],
        "rationale": "x",
    }
    valid, errors = validate_proposal_deterministic(proposal, ["NOOP", "TICK", "MOVE"])
    assert valid is False
    assert any("args." in e and "required" in e for e in errors)


def test_validator_args_required_for_start_run() -> None:
    """START_RUN without device_id is invalid."""
    proposal = {
        "action_type": "START_RUN",
        "args": {},
        "reason_code": None,
        "token_refs": [],
        "rationale": "x",
    }
    valid, errors = validate_proposal_deterministic(proposal, ["NOOP", "TICK", "START_RUN"])
    assert valid is False
    assert any("device_id" in e for e in errors)


def test_validator_structured_errors_non_sensitive() -> None:
    """Structured errors are short and contain no PII or raw schema."""
    proposal = {"action_type": "OPEN_DOOR", "args": {}}
    valid, errors = validate_proposal_deterministic(proposal, ["NOOP", "OPEN_DOOR"])
    assert valid is False
    for e in errors:
        assert len(e) < 80
        assert "password" not in e.lower()
        assert "token" not in e or "token_refs" in e or "restricted" in e


def test_rc_llm_proposed_invalid_constant() -> None:
    """RC_LLM_PROPOSED_INVALID is defined for BLOCKED recording."""
    assert RC_LLM_PROPOSED_INVALID == "RC_LLM_PROPOSED_INVALID"


def test_agent_proposed_invalid_no_repair_when_deterministic() -> None:
    """In deterministic mode, proposal that fails deterministic validation yields NOOP with RC_LLM_PROPOSED_INVALID and repair_attempted=False."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.baselines.llm.agent import (
        LLMAgentWithShield,
        _build_repair_user_content_structured,
    )
    from labtrust_gym.pipeline import get_pipeline_mode, set_pipeline_config

    set_pipeline_config(pipeline_mode="deterministic", allow_network=False)
    assert get_pipeline_mode() == "deterministic"

    class BackendReturnsMoveNoArgs:
        """Returns one MOVE with empty args (fails args schema in validator)."""

        def generate(self, messages):
            return '{"action_type":"MOVE","args":{},"reason_code":null,"token_refs":[],"rationale":"POLICY:RBAC:allowed_actions MOVE.","confidence":0.9,"safety_notes":""}'

    rbac = {
        "roles": [{"role_id": "ROLE_RECEPTION", "allowed_actions": ["NOOP", "TICK", "MOVE"]}],
        "agents": {"ops_0": "ROLE_RECEPTION"},
    }
    agent = LLMAgentWithShield(
        backend=BackendReturnsMoveNoArgs(),
        rbac_policy=rbac,
        pz_to_engine={"ops_0": "A_RECEPTION"},
        use_action_proposal_schema=True,
    )
    agent.reset(seed=42, partner_id="", timing_mode="explicit")
    obs = {
        "zone_id": "Z_SRA_RECEPTION",
        "site_id": "SITE_HUB",
        "t_s": 0,
        "queue_by_device": [],
        "log_frozen": 0,
        "role_id": "ROLE_RECEPTION",
    }
    _, action_info, meta = agent.act(obs, agent_id="ops_0")
    assert action_info.get("action_type") == "NOOP"
    assert meta.get("_shield_reason_code") == RC_LLM_PROPOSED_INVALID
    llm = meta.get("_llm_decision") or {}
    assert llm.get("error_code") == RC_LLM_PROPOSED_INVALID
    assert llm.get("repair_attempted") is False

    assert "VALIDATION_ERRORS" in _build_repair_user_content_structured(
        "[]", "{}", ["action_type not in allowed_actions"]
    )
