"""Smoke tests for llm_central_planner_debate (debate/consensus) coordination method."""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.baselines.coordination.methods.llm_central_planner_debate import (
    LLMCentralPlannerDebate,
    _majority_merge_proposals,
)
from labtrust_gym.baselines.coordination.methods.llm_central_planner import (
    DeterministicProposalBackend,
)


def test_debate_majority_merge_two_proposals() -> None:
    """Majority merge: two proposals with same action_type per agent yields that action."""
    proposals = [
        {
            "per_agent": [
                {"agent_id": "ops_0", "action_type": "TICK", "args": {}},
                {"agent_id": "runner_0", "action_type": "NOOP", "args": {}},
            ],
        },
        {
            "per_agent": [
                {"agent_id": "ops_0", "action_type": "TICK", "args": {}},
                {"agent_id": "runner_0", "action_type": "NOOP", "args": {}},
            ],
        },
    ]
    merged = _majority_merge_proposals(
        proposals,
        agent_ids=["ops_0", "runner_0"],
        allowed_actions=["NOOP", "TICK"],
        step_id=0,
        method_id="test",
    )
    assert merged["per_agent"][0]["action_type"] == "TICK"
    assert merged["per_agent"][1]["action_type"] == "NOOP"


def test_debate_majority_merge_tie_break() -> None:
    """Majority merge: 2 NOOP vs 1 TICK yields NOOP (majority)."""
    proposals = [
        {"per_agent": [{"agent_id": "a", "action_type": "NOOP", "args": {}}]},
        {"per_agent": [{"agent_id": "a", "action_type": "NOOP", "args": {}}]},
        {"per_agent": [{"agent_id": "a", "action_type": "TICK", "args": {}}]},
    ]
    merged = _majority_merge_proposals(
        proposals,
        agent_ids=["a"],
        allowed_actions=["NOOP", "TICK"],
        step_id=0,
        method_id="test",
    )
    assert merged["per_agent"][0]["action_type"] == "NOOP"


def test_llm_central_planner_debate_propose_actions() -> None:
    """LLMCentralPlannerDebate with 2 deterministic proposers returns valid actions."""
    backends = [
        DeterministicProposalBackend(seed=1, default_action_type="NOOP"),
        DeterministicProposalBackend(seed=2, default_action_type="TICK"),
    ]
    method = LLMCentralPlannerDebate(
        proposal_backend=backends,
        rbac_policy={},
        allowed_actions=["NOOP", "TICK"],
        aggregator="majority",
    )
    method.reset(seed=0, policy={}, scale_config={})
    obs = {"ops_0": {"queue_has_head": []}, "runner_0": {"queue_has_head": []}}
    actions = method.propose_actions(obs, {}, 0)
    assert set(actions.keys()) == {"ops_0", "runner_0"}
    for aid in actions:
        assert "action_index" in actions[aid]
        assert "action_type" in actions[aid]
    assert method._last_proposal is not None


def test_registry_creates_llm_central_planner_debate() -> None:
    """Registry instantiates llm_central_planner_debate with deterministic proposers."""
    from labtrust_gym.baselines.coordination.registry import make_coordination_method

    repo_root = Path(__file__).resolve().parent.parent
    policy = {}
    scale_config = {"seed": 42, "coord_debate_proposers": 2, "coord_debate_aggregator": "majority"}
    method = make_coordination_method(
        "llm_central_planner_debate",
        policy,
        repo_root=repo_root,
        scale_config=scale_config,
    )
    assert method.method_id == "llm_central_planner_debate"
    method.reset(seed=42, policy=policy, scale_config=scale_config)
    obs = {"ops_0": {}, "runner_0": {}}
    actions = method.propose_actions(obs, {}, 0)
    assert set(actions.keys()) == {"ops_0", "runner_0"}
