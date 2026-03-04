"""
Smoke tests for LLM hierarchical allocator: deterministic backend produces
stable proposals with SET_INTENT; local controller (greedy/EDF/WHCA) translates
to concrete actions. Compare to deterministic hierarchical baselines on throughput
vs violations and resilience under comms poison.
"""

from __future__ import annotations

from labtrust_gym.baselines.coordination.llm_contract import validate_proposal
from labtrust_gym.baselines.coordination.local_controller import (
    _job_id,
    intent_to_actions,
)
from labtrust_gym.baselines.coordination.methods.llm_hierarchical_allocator import (
    SET_INTENT,
    DeterministicAssignmentsBackend,
    LLMHierarchicalAllocator,
)


def _minimal_rbac() -> dict:
    return {
        "version": "0.1",
        "roles": {"ROLE": {"allowed_actions": ["NOOP", "TICK", "QUEUE_RUN", "MOVE", "START_RUN"]}},
        "agents": {"ops_0": "ROLE", "runner_0": "ROLE"},
        "action_constraints": {},
    }


def test_job_id_format() -> None:
    """Job id format is deterministic and matches local_controller resolution."""
    assert _job_id("D1", "W1") == "D1:W1"
    assert _job_id("DEV_A", "STAT_1") == "DEV_A:STAT_1"


def test_deterministic_assignments_backend_proposal_validates() -> None:
    """Deterministic backend produces CoordinationProposal with SET_INTENT that validates."""
    backend = DeterministicAssignmentsBackend(seed=42)
    digest = {
        "step": 0,
        "per_agent": [
            {"agent_id": "ops_0", "zone": "Z_A"},
            {"agent_id": "runner_0", "zone": "Z_A"},
        ],
        "per_device": [
            {"device_id": "D1", "queue_head": "W1", "state": "busy"},
        ],
        "device_zone": {"D1": "Z_A"},
    }
    allowed = [SET_INTENT, "NOOP", "TICK"]
    proposal, meta = backend.generate_proposal(digest, allowed, step_id=0, method_id="llm_hierarchical_allocator")
    valid, errors = validate_proposal(proposal, allowed_actions=allowed)
    assert valid, errors
    assert proposal.get("method_id") == "llm_hierarchical_allocator"
    per_agent = proposal.get("per_agent") or []
    assert len(per_agent) >= 1
    for pa in per_agent:
        assert pa.get("action_type") == SET_INTENT
        assert "job_id" in (pa.get("args") or {})
    assert meta.get("backend_id") == "deterministic_assignments"


def test_deterministic_backend_stable_proposal_same_digest_step() -> None:
    """Same digest and step_id yield same proposal (stable for benchmarking)."""
    backend = DeterministicAssignmentsBackend(seed=99)
    digest = {
        "step": 0,
        "per_agent": [{"agent_id": "ops_0", "zone": "Z"}],
        "per_device": [{"device_id": "D0", "queue_head": "W0"}],
        "device_zone": {"D0": "Z"},
    }
    allowed = [SET_INTENT]
    p1, _ = backend.generate_proposal(digest, allowed, step_id=0, method_id="llm_hierarchical_allocator")
    p2, _ = backend.generate_proposal(digest, allowed, step_id=0, method_id="llm_hierarchical_allocator")
    assert p1.get("proposal_id") == p2.get("proposal_id")
    assert p1.get("per_agent") == p2.get("per_agent")


def test_intent_to_actions_returns_concrete_actions() -> None:
    """Local controller translates SET_INTENT proposal to concrete action_dict."""
    proposal = {
        "proposal_id": "test",
        "step_id": 0,
        "method_id": "llm_hierarchical_allocator",
        "per_agent": [
            {
                "agent_id": "ops_0",
                "action_type": SET_INTENT,
                "args": {"job_id": "D0:W0", "priority_weight": 1},
                "reason_code": "COORD_HIER_ASSIGN",
            },
        ],
        "comms": [],
        "meta": {},
    }
    obs = {
        "ops_0": {
            "my_zone_idx": 1,
            "queue_by_device": [{"device_id": "D0", "queue_head": "W0", "queue_len": 1}],
            "queue_has_head": [1],
        },
        "runner_0": {"my_zone_idx": 1, "queue_by_device": [], "queue_has_head": []},
    }
    agent_ids = ["ops_0", "runner_0"]
    zone_ids = ["Z_A"]
    device_ids = ["D0"]
    device_zone = {"D0": "Z_A"}
    policy = {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}],
            "device_placement": [{"device_id": "D0", "zone_id": "Z_A"}],
            "graph_edges": [],
        }
    }
    actions = intent_to_actions(
        proposal,
        obs,
        agent_ids,
        zone_ids,
        device_ids,
        device_zone,
        policy,
        t=0,
        seed=42,
        strategy="edf",
    )
    assert set(actions.keys()) == {"ops_0", "runner_0"}
    for aid, ad in actions.items():
        assert "action_index" in ad
        assert "action_type" in ad
        assert ad["action_type"] in ("NOOP", "MOVE", "START_RUN")


def test_llm_hierarchical_allocator_propose_actions_deterministic() -> None:
    """LLMHierarchicalAllocator.propose_actions returns actions; same seed gives same outcome."""
    backend = DeterministicAssignmentsBackend(seed=0)
    rbac = _minimal_rbac()
    planner = LLMHierarchicalAllocator(
        allocator_backend=backend,
        rbac_policy=rbac,
        allowed_actions=["NOOP", "TICK", "QUEUE_RUN", "MOVE", "START_RUN"],
        local_strategy="edf",
    )
    planner.reset(seed=42, policy={}, scale_config={})
    obs = {
        "ops_0": {"my_zone_idx": 1, "queue_by_device": []},
        "runner_0": {"my_zone_idx": 1, "queue_by_device": []},
    }
    a1 = planner.propose_actions(obs, {}, 0)
    a2 = planner.propose_actions(obs, {}, 0)
    assert set(a1.keys()) == set(a2.keys()) == {"ops_0", "runner_0"}
    for aid in a1:
        assert a1[aid].get("action_index") == a2[aid].get("action_index")
        assert a1[aid].get("action_type") == a2[aid].get("action_type")


def test_llm_hierarchical_allocator_nominal_allocations_cover_work() -> None:
    """Under nominal conditions (same zone as work, no frozen), allocations cover work."""
    backend = DeterministicAssignmentsBackend(seed=0)
    policy = {
        "pz_to_engine": {"ops_0": "ops_0", "runner_0": "runner_0"},
        "policy_summary": {},
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}],
            "device_placement": [{"device_id": "D1", "zone_id": "Z_A"}, {"device_id": "D2", "zone_id": "Z_A"}],
            "graph_edges": [],
        },
    }
    get_allowed = lambda aid: ["NOOP", "TICK", "MOVE", "START_RUN", SET_INTENT]
    allocator = LLMHierarchicalAllocator(
        allocator_backend=backend,
        rbac_policy={},
        allowed_actions=["NOOP", "TICK", "MOVE", "START_RUN"],
        get_allowed_actions_fn=get_allowed,
        local_strategy="edf",
    )
    allocator.reset(seed=42, policy=policy, scale_config={})
    obs = {
        "ops_0": {
            "my_zone_idx": 0,
            "zone_id": "Z_A",
            "queue_by_device": [
                {"device_id": "D1", "queue_head": "W1", "queue_len": 1},
                {"device_id": "D2", "queue_head": "W2", "queue_len": 1},
            ],
            "queue_has_head": [1, 1],
        },
        "runner_0": {
            "my_zone_idx": 0,
            "zone_id": "Z_A",
            "queue_by_device": [
                {"device_id": "D1", "queue_head": "W1", "queue_len": 1},
                {"device_id": "D2", "queue_head": "W2", "queue_len": 1},
            ],
            "queue_has_head": [1, 1],
        },
    }
    infos = {"ops_0": {}, "runner_0": {}}
    actions = allocator.propose_actions(obs, infos, 0)
    assert set(actions.keys()) == {"ops_0", "runner_0"}
    valid_types = {"NOOP", "MOVE", "START_RUN"}
    for aid, rec in actions.items():
        assert rec.get("action_type") in valid_types
    n_start_run = sum(1 for r in actions.values() if (r.get("action_type") or "") == "START_RUN")
    assert n_start_run >= 1
    assert n_start_run <= 2


def test_hierarchical_low_confidence_fallback() -> None:
    """Low intent_confidence -> controller falls back to kernel (empty assignments)."""
    backend = DeterministicAssignmentsBackend(seed=0, low_confidence=True)
    policy = {
        "pz_to_engine": {"a1": "r1"},
        "policy_summary": {},
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}],
            "device_placement": [{"device_id": "D1", "zone_id": "Z_A"}],
            "graph_edges": [],
        },
    }
    allocator = LLMHierarchicalAllocator(
        allocator_backend=backend,
        rbac_policy={},
        allowed_actions=["NOOP", "TICK", "MOVE", SET_INTENT],
        local_strategy="edf",
    )
    allocator.reset(seed=0, policy=policy, scale_config={"confidence_threshold": 0.5})
    obs = {
        "a1": {
            "zone_id": "Z_A",
            "queue_by_device": [{"device_id": "D1", "queue_head": "W1", "queue_len": 1}],
            "queue_has_head": [1],
        },
    }
    actions = allocator.propose_actions(obs, {}, 0)
    assert "a1" in actions
    assert actions["a1"].get("action_index") is not None


def test_hierarchical_assumption_mismatch_reject() -> None:
    """Wrong assumptions (e.g. agent in Z_WRONG) -> controller rejects and returns NOOP."""
    backend = DeterministicAssignmentsBackend(seed=0, wrong_assumptions=True)
    policy = {
        "pz_to_engine": {"a1": "r1"},
        "policy_summary": {},
        "zone_layout": {"zones": [{"zone_id": "Z_A"}], "device_placement": [], "graph_edges": []},
    }
    allocator = LLMHierarchicalAllocator(
        allocator_backend=backend,
        rbac_policy={},
        allowed_actions=["NOOP", "TICK", "MOVE", SET_INTENT],
        local_strategy="edf",
    )
    allocator.reset(seed=0, policy=policy, scale_config={})
    obs = {"a1": {"zone_id": "Z_A", "queue_by_device": []}}
    actions = allocator.propose_actions(obs, {}, 0)
    assert actions["a1"]["action_index"] == 0


def test_registry_creates_llm_hierarchical_allocator() -> None:
    """Registry instantiates llm_hierarchical_allocator with deterministic backend."""
    from pathlib import Path

    from labtrust_gym.baselines.coordination.registry import make_coordination_method

    repo_root = Path(__file__).resolve().parent.parent
    policy = {"pz_to_engine": {"worker_0": "ops_0", "worker_1": "runner_0"}}
    scale_config = {"seed": 123}
    method = make_coordination_method(
        "llm_hierarchical_allocator",
        policy,
        repo_root=repo_root,
        scale_config=scale_config,
        pz_to_engine={"worker_0": "ops_0", "worker_1": "runner_0"},
    )
    assert method.method_id == "llm_hierarchical_allocator"
    method.reset(seed=123, policy=policy, scale_config=scale_config)
    obs = {"ops_0": {}, "runner_0": {}}
    actions = method.propose_actions(obs, {}, 0)
    assert set(actions.keys()) == {"ops_0", "runner_0"}
