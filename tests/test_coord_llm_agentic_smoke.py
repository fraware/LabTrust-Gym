"""Smoke tests for llm_central_planner_agentic (coordinator ReAct/tools) method."""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.baselines.coordination.methods.llm_central_planner_agentic import (
    LLMCentralPlannerAgentic,
    DeterministicAgenticProposalBackend,
)
from labtrust_gym.baselines.coordination.methods.coord_agentic_tools import (
    run_tools,
    DEFAULT_COORD_TOOL_REGISTRY,
)


def test_agentic_tool_run() -> None:
    """run_tools executes query_queue_state and returns result."""
    results = run_tools(
        [{"name": "query_queue_state", "args": {}}],
        obs={"ops_0": {"queue_has_head": [1]}},
        infos={},
        step_t=0,
        method_state={},
        registry=DEFAULT_COORD_TOOL_REGISTRY,
    )
    assert len(results) == 1
    assert results[0]["name"] == "query_queue_state"
    assert "result" in results[0]
    assert "agents" in results[0]["result"] or "step" in results[0]["result"]


def test_agentic_backend_first_call_returns_tool_calls() -> None:
    """DeterministicAgenticProposalBackend returns tool_calls on first call, proposal on second."""
    backend = DeterministicAgenticProposalBackend(seed=0)
    digest = {"per_agent": [{"agent_id": "ops_0"}, {"agent_id": "runner_0"}]}
    prop1, meta1 = backend.generate_proposal(
        digest, ["NOOP", "TICK"], step_id=0, method_id="test"
    )
    assert meta1.get("tool_calls") == [{"name": "query_queue_state", "args": {}}]
    prop2, meta2 = backend.generate_proposal(
        digest, ["NOOP", "TICK"], step_id=0, method_id="test"
    )
    assert not meta2.get("tool_calls")
    assert prop2.get("per_agent")
    assert len(prop2["per_agent"]) == 2


def test_llm_central_planner_agentic_propose_actions() -> None:
    """LLMCentralPlannerAgentic runs tool round then uses final proposal."""
    backend = DeterministicAgenticProposalBackend(seed=1)
    method = LLMCentralPlannerAgentic(
        proposal_backend=backend,
        rbac_policy={},
        allowed_actions=["NOOP", "TICK"],
        max_tool_rounds=5,
    )
    method.reset(seed=0, policy={}, scale_config={})
    obs = {"ops_0": {"queue_has_head": []}, "runner_0": {"queue_has_head": []}}
    actions = method.propose_actions(obs, {}, 0)
    assert set(actions.keys()) == {"ops_0", "runner_0"}
    for aid in actions:
        assert "action_index" in actions[aid]
        assert "action_type" in actions[aid]
    assert method._last_proposal is not None


def test_registry_creates_llm_central_planner_agentic() -> None:
    """Registry instantiates llm_central_planner_agentic with deterministic agentic backend."""
    from labtrust_gym.baselines.coordination.registry import make_coordination_method

    repo_root = Path(__file__).resolve().parent.parent
    policy = {}
    scale_config = {"seed": 43, "coord_agentic_max_rounds": 5}
    method = make_coordination_method(
        "llm_central_planner_agentic",
        policy,
        repo_root=repo_root,
        scale_config=scale_config,
    )
    assert method.method_id == "llm_central_planner_agentic"
    method.reset(seed=43, policy=policy, scale_config=scale_config)
    obs = {"ops_0": {}, "runner_0": {}}
    actions = method.propose_actions(obs, {}, 0)
    assert set(actions.keys()) == {"ops_0", "runner_0"}
