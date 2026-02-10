"""
One-shot repair loop for invalid ActionProposal.

- Canned invalid output -> repair returns valid action.
- Only one extra backend call (no retries).
- LLM_DECISION includes repair_attempted, repair_succeeded, repair_*_sha256.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.baselines.llm.agent import (
    LLMAgentWithShield,
    _build_repair_user_content,
    _try_repair,
)


class _RepairMockBackend:
    """First call returns invalid ActionProposal; second call (repair) returns valid."""

    backend_id = "repair_mock"
    model_id = "n/a"
    _call_count = 0

    def generate(self, messages: list[dict[str, str]]) -> str:
        self._call_count += 1
        if self._call_count == 1:
            return '{"action_type": "TICK", "args": {}}'
        user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        if "VALIDATION_ERROR" in user and "INVALID_ACTION_PROPOSAL" in user:
            return (
                '{"action_type": "TICK", "args": {}, "reason_code": null, '
                '"token_refs": [], "rationale": "POLICY:RBAC:allowed_actions repair", '
                '"confidence": 0.9, "safety_notes": ""}'
            )
        return (
            '{"action_type": "NOOP", "args": {}, "reason_code": null, '
            '"token_refs": [], "rationale": "fallback", '
            '"confidence": 0.0, "safety_notes": ""}'
        )


def test_repair_user_content_shape() -> None:
    """Repair user message contains allowed_actions, invalid proposal, validation_error."""
    user = _build_repair_user_content(
        '["NOOP", "TICK"]',
        '{"action_type": "TICK"}',
        "LLM_INVALID_SCHEMA",
    )
    assert "ALLOWED_ACTIONS_JSON" in user
    assert "INVALID_ACTION_PROPOSAL" in user
    assert "VALIDATION_ERROR" in user
    assert "LLM_INVALID_SCHEMA" in user


def test_try_repair_one_extra_call() -> None:
    """_try_repair calls backend once (no retries)."""
    call_count = 0

    class OneCallBackend:
        def generate(self, messages: list[dict[str, str]]) -> str:
            nonlocal call_count
            call_count += 1
            return (
                '{"action_type": "TICK", "args": {}, "reason_code": null, '
                '"token_refs": [], "rationale": "fixed", '
                '"confidence": 0.9, "safety_notes": ""}'
            )

    backend = OneCallBackend()
    repaired_text, rp_sha, rr_sha = _try_repair(
        backend,
        '["NOOP", "TICK"]',
        {"action_type": "TICK", "args": {}},
        "MISSING_RATIONALE",
    )
    assert call_count == 1
    assert repaired_text is not None
    assert rp_sha is not None and len(rp_sha) == 64
    assert rr_sha is not None and len(rr_sha) == 64


def test_repair_invalid_then_valid_returns_action() -> None:
    """Canned invalid first response -> repair returns valid -> agent returns TICK."""
    from labtrust_gym.pipeline import set_pipeline_config

    set_pipeline_config("llm_live", allow_network=False)
    try:
        backend = _RepairMockBackend()
        rbac = {
            "roles": [{"role_id": "ops", "allowed_actions": ["NOOP", "TICK"]}],
            "agents": {"ops_0": "ops"},
        }
        agent = LLMAgentWithShield(
            backend=backend,
            rbac_policy=rbac,
            pz_to_engine={"ops_0": "ops_0"},
            use_action_proposal_schema=True,
        )
        agent.reset(seed=42)
        obs = {"t_s": 0, "zone_id": "Z_SRA_RECEPTION", "queue_by_device": []}
        action_index, action_info, meta = agent.act(obs, agent_id="ops_0")
        assert backend._call_count == 2
    finally:
        set_pipeline_config("deterministic", allow_network=False)
    llm = meta.get("_llm_decision")
    assert llm is not None
    assert llm.get("repair_attempted") is True
    assert llm.get("repair_succeeded") is True
    assert "repair_prompt_sha256" in llm and len(llm.get("repair_prompt_sha256", "")) == 64
    assert "repair_response_sha256" in llm and len(llm.get("repair_response_sha256", "")) == 64
    assert action_info.get("action_type") == "TICK"
    assert action_index == 1


def test_repair_fails_then_noop() -> None:
    """When repair also returns invalid, agent returns NOOP with repair_succeeded=False."""
    from labtrust_gym.pipeline import set_pipeline_config

    call_count = 0

    class AlwaysInvalidBackend:
        def generate(self, messages: list[dict[str, str]]) -> str:
            nonlocal call_count
            call_count += 1
            return '{"action_type": "TICK"}'

    set_pipeline_config("llm_live", allow_network=False)
    try:
        backend = AlwaysInvalidBackend()
        rbac = {
            "roles": [{"role_id": "ops", "allowed_actions": ["NOOP", "TICK"]}],
            "agents": {"ops_0": "ops"},
        }
        agent = LLMAgentWithShield(
            backend=backend,
            rbac_policy=rbac,
            pz_to_engine={"ops_0": "ops_0"},
            use_action_proposal_schema=True,
        )
        agent.reset(seed=42)
        obs = {"t_s": 0, "zone_id": "Z_SRA_RECEPTION", "queue_by_device": []}
        action_index, action_info, meta = agent.act(obs, agent_id="ops_0")
        assert call_count == 2
    finally:
        set_pipeline_config("deterministic", allow_network=False)
    llm = meta.get("_llm_decision")
    assert llm is not None
    assert llm.get("repair_attempted") is True
    assert llm.get("repair_succeeded") is False
    assert action_info.get("action_type") == "NOOP"
    assert action_index == 0


def test_deterministic_baseline_no_repair_when_valid() -> None:
    """DeterministicConstrainedBackend returns valid on first call -> no repair, same behavior."""
    from labtrust_gym.baselines.llm.agent import DeterministicConstrainedBackend

    backend = DeterministicConstrainedBackend(seed=99)
    rbac = {
        "roles": [{"role_id": "ops", "allowed_actions": ["NOOP", "TICK"]}],
        "agents": {"ops_0": "ops"},
    }
    agent = LLMAgentWithShield(
        backend=backend,
        rbac_policy=rbac,
        pz_to_engine={"ops_0": "ops_0"},
        use_action_proposal_schema=True,
    )
    agent.reset(seed=99)
    obs = {"t_s": 0, "zone_id": "Z_SRA_RECEPTION", "queue_by_device": []}
    action_index, action_info, meta = agent.act(obs, agent_id="ops_0")
    llm = meta.get("_llm_decision")
    assert llm is not None
    assert llm.get("repair_attempted") is False
    assert llm.get("repair_succeeded") is False
    assert "repair_prompt_sha256" not in llm or llm.get("repair_prompt_sha256") is None
