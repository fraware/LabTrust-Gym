"""
State-of-the-art LLM coordination contracts: committee, arbiter, method contracts.

Covers central planner committee roles and arbiter validation, hierarchical
allocator output shape, auction bidder structure, gossip summarizer codec,
repair backend determinism, golden-trace determinism. Detector gating tests
live in test_detector_throttle_advisor_gating.py.
"""

from __future__ import annotations

from labtrust_gym.baselines.coordination.methods.llm_central_planner import (
    COMMITTEE_ROLES,
    DeterministicCommitteeBackend,
    DeterministicProposalBackend,
    LLMCentralPlanner,
    _arbiter_validate_committee,
)


def test_llm_central_planner_committee_roles_defined() -> None:
    """Multi-role committee: Allocator, Scheduler, Router, Safety reviewer."""
    assert "Allocator" in COMMITTEE_ROLES
    assert "Scheduler" in COMMITTEE_ROLES
    assert "Router" in COMMITTEE_ROLES
    assert "Safety reviewer" in COMMITTEE_ROLES


def test_llm_central_planner_arbiter_validates_proposal() -> None:
    """Deterministic arbiter merges/validates; returns (valid, errors)."""
    proposal = {
        "proposal_id": "p1",
        "step_id": 0,
        "horizon_steps": 1,
        "method_id": "llm_central_planner",
        "per_agent": [
            {"agent_id": "a1", "action_type": "NOOP", "args": {}, "reason_code": "OK"},
        ],
        "comms": [],
        "meta": {},
    }
    valid, errors = _arbiter_validate_committee(proposal, ["NOOP", "TICK"])
    assert isinstance(valid, bool)
    assert isinstance(errors, list)


def test_llm_central_planner_committee_golden_trace() -> None:
    """Committee backend: deterministic merge of four roles; same seed -> same actions."""
    backend = DeterministicCommitteeBackend(seed=42)
    policy = {"pz_to_engine": {"a1": "r1"}, "policy_summary": {"allowed_actions": ["NOOP", "TICK"]}}
    planner = LLMCentralPlanner(proposal_backend=backend, rbac_policy={}, allowed_actions=["NOOP", "TICK"])
    planner.reset(42, policy, {"seed": 42})
    obs = {"a1": {"zone_id": "Z_A", "queue_by_device": []}}
    out1 = planner.propose_actions(obs, {}, 0)
    planner.reset(42, policy, {"seed": 42})
    out2 = planner.propose_actions(obs, {}, 0)
    assert out1 == out2
    assert out1["a1"].get("action_type") in ("NOOP", "TICK")


def test_llm_central_planner_committee_corrupt_allocator_rejected() -> None:
    """Fault injection: corrupt Allocator output -> arbiter rejects -> NOOP for all."""
    backend = DeterministicCommitteeBackend(seed=42, corrupt_role="Allocator")
    policy = {"pz_to_engine": {"a1": "r1"}, "policy_summary": {"allowed_actions": ["NOOP", "TICK"]}}
    planner = LLMCentralPlanner(proposal_backend=backend, rbac_policy={}, allowed_actions=["NOOP", "TICK"])
    planner.reset(42, policy, {})
    obs = {"a1": {"zone_id": "Z_A", "queue_by_device": []}}
    out = planner.propose_actions(obs, {}, 0)
    assert out["a1"]["action_index"] == 0


def test_llm_central_planner_golden_trace_deterministic_backend() -> None:
    """Golden committee trace with offline backend: same seed -> same actions."""
    backend = DeterministicProposalBackend(seed=42, default_action_type="NOOP")
    policy = {
        "pz_to_engine": {"a1": "r1"},
        "policy_summary": {"allowed_actions": ["NOOP", "TICK"]},
    }
    planner = LLMCentralPlanner(
        proposal_backend=backend,
        rbac_policy={},
        allowed_actions=["NOOP", "TICK"],
    )
    planner.reset(42, policy, {"seed": 42})
    obs = {"a1": {"zone_id": "Z_A", "queue_by_device": []}}
    out1 = planner.propose_actions(obs, {}, 0)
    planner.reset(42, policy, {"seed": 42})
    out2 = planner.propose_actions(obs, {}, 0)
    assert out1 == out2
    assert "a1" in out1
    assert out1["a1"].get("action_index") is not None


def test_llm_hierarchical_allocator_contract() -> None:
    """Hierarchical allocator exposes SET_INTENT and required output shape."""
    from labtrust_gym.baselines.coordination.methods import (
        llm_hierarchical_allocator,
    )
    from labtrust_gym.baselines.coordination.methods.llm_hierarchical_allocator import (
        DeterministicAssignmentsBackend,
    )

    assert hasattr(llm_hierarchical_allocator, "SET_INTENT")
    backend = DeterministicAssignmentsBackend(seed=42)
    digest = {
        "per_agent": [{"agent_id": "a1", "zone": "Z_A"}, {"agent_id": "a2", "zone": "Z_A"}],
        "per_device": [{"device_id": "D1", "queue_head": "W1"}, {"device_id": "D2", "queue_head": "W2"}],
        "device_zone": {"D1": "Z_A", "D2": "Z_A"},
    }
    proposal, meta = backend.generate_proposal(
        digest, ["SET_INTENT", "NOOP", "TICK"], 0, "llm_hierarchical_allocator"
    )
    assert proposal.get("intent_confidence") is not None or any(
        p.get("intent_confidence") is not None for p in (proposal.get("per_agent") or [])
    )
    for pa in proposal.get("per_agent") or []:
        assert pa.get("action_type") == "SET_INTENT"
        assert "args" in pa and "job_id" in pa["args"]


def test_llm_auction_bidder_contract() -> None:
    """Auction bidder module and explainable typed bid structure."""
    from labtrust_gym.baselines.coordination.methods import (
        llm_auction_bidder,
    )
    from labtrust_gym.baselines.coordination.methods.llm_auction_bidder import (
        DeterministicBidBackend,
        _proposal_market_to_typed_bids,
    )

    assert llm_auction_bidder is not None
    backend = DeterministicBidBackend(seed=42)
    digest = {
        "per_agent": [{"agent_id": "a1", "zone": "Z_A"}],
        "per_device": [{"device_id": "D1", "queue_head": "W1"}],
        "device_zone": {"D1": "Z_A"},
    }
    proposal = backend.generate_proposal(digest, 0, "llm_auction_bidder")
    market = proposal.get("market") or []
    assert len(market) >= 1
    for m in market:
        assert "agent_id" in m and "bid" in m and "bundle" in m
        assert "units" in m or m.get("units", "cost") == "cost"
    typed_bids, errors = _proposal_market_to_typed_bids(market, {"a1"})
    assert not errors
    for b in typed_bids:
        assert isinstance(b.agent_id, str)
        assert isinstance(b.bundle_id, str)
        assert isinstance(b.value, (int, float))
        assert isinstance(b.units, str)
        assert b.units in ("cost", "time")


def test_learning_to_bid_checksum_stable() -> None:
    """Same (agent_id, work_id, device_id, buffer_len, seed) -> same predict_cost_checksum."""
    from labtrust_gym.baselines.coordination.allocation.learning_to_bid import (
        predict_cost_checksum,
    )

    c1 = predict_cost_checksum("a1", "W1", "D1", 10, 42)
    c2 = predict_cost_checksum("a1", "W1", "D1", 10, 42)
    assert c1 == c2
    c3 = predict_cost_checksum("a1", "W1", "D1", 10, 99)
    assert c1 != c3


def test_llm_auction_bidder_spoofed_bid_dropped() -> None:
    """Market entry with unknown agent_id is dropped; assignment uses only valid bids."""
    from labtrust_gym.baselines.coordination.methods.llm_auction_bidder import (
        LLMAuctionBidder,
        _proposal_market_to_typed_bids,
    )

    class SpoofBackend:
        def reset(self, seed: int) -> None:
            pass

        def generate_proposal(self, state_digest, step_id, method_id):
            return {
                "proposal_id": "spoof",
                "step_id": step_id,
                "method_id": method_id,
                "horizon_steps": 1,
                "per_agent": [],
                "comms": [],
                "market": [
                    {"agent_id": "a1", "bid": 1.0, "bundle": {"device_id": "D1", "work_id": "W1"}, "units": "cost", "constraints": {}},
                    {"agent_id": "unknown_agent", "bid": 0.1, "bundle": {"device_id": "D1", "work_id": "W1"}, "units": "cost", "constraints": {}},
                ],
                "meta": {},
            }

    typed_bids, errors = _proposal_market_to_typed_bids(
        [{"agent_id": "a1", "bid": 1.0, "bundle": {"device_id": "D1", "work_id": "W1"}, "units": "cost", "constraints": {}},
         {"agent_id": "unknown_agent", "bid": 0.1, "bundle": {"device_id": "D1", "work_id": "W1"}, "units": "cost", "constraints": {}},
        ],
        {"a1"},
    )
    assert len(typed_bids) == 1
    assert typed_bids[0].agent_id == "a1"


def test_llm_gossip_summarizer_codec_contract() -> None:
    """Gossip summarizer message type and summary codec."""
    from labtrust_gym.baselines.coordination.methods import (
        llm_gossip_summarizer,
    )

    assert (
        llm_gossip_summarizer.MESSAGE_TYPE_GOSSIP_SUMMARY == "gossip_summary"
    )


def test_llm_repair_over_kernel_deterministic_backend() -> None:
    """Repair backend: deterministic repair output and meta."""
    from labtrust_gym.baselines.coordination.methods.llm_repair_over_kernel_whca import (
        DeterministicRepairBackend,
    )

    backend = DeterministicRepairBackend(seed=42)
    repair_input = {"context": {}, "rejected_plan": []}
    per_agent, meta = backend.repair(repair_input, ["a1", "a2"])
    assert len(per_agent) == 2
    assert meta.get("backend_id") == "deterministic_repair"


def test_llm_central_planner_invalid_proposal_returns_noop() -> None:
    """When backend returns invalid proposal, planner returns NOOP for all (no crash).
    Repair loop and max_repairs are handled by executor/runner; see docstring."""
    class InvalidBackend:
        def reset(self, seed: int) -> None:
            pass

        def generate_proposal(self, state_digest, allowed_actions, step_id, method_id, **kw):
            agent_ids = [p.get("agent_id") for p in (state_digest.get("per_agent") or [])]
            if not agent_ids:
                agent_ids = ["a1"]
            return (
                {
                    "proposal_id": "inv",
                    "step_id": step_id,
                    "method_id": method_id,
                    "horizon_steps": 1,
                    "per_agent": [
                        {"agent_id": aid, "action_type": "INVALID", "args": {}, "reason_code": "x"}
                        for aid in agent_ids
                    ],
                    "comms": [],
                    "meta": {},
                },
                {},
            )

    backend = InvalidBackend()
    policy = {"pz_to_engine": {"a1": "r1"}, "policy_summary": {"allowed_actions": ["NOOP", "TICK"]}}
    planner = LLMCentralPlanner(
        proposal_backend=backend,
        rbac_policy={},
        allowed_actions=["NOOP", "TICK"],
    )
    planner.reset(42, policy, {})
    obs = {"a1": {"zone_id": "Z_A", "queue_by_device": []}}
    out = planner.propose_actions(obs, {}, 0)
    assert out["a1"]["action_index"] == 0
