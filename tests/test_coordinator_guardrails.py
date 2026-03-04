"""
Coordinator guardrails: circuit breaker and rate limiter for coordinator backends.

Unit and integration tests that the coordinator guardrail wrappers return safe
fallback (NOOP proposal / NOOP repair) with correct reason code when circuit
is open, rate limit exceeded, or inner backend raises (e.g. 429/timeout). No real API.
"""

from __future__ import annotations

from labtrust_gym.baselines.llm.coordinator_throttle import (
    CoordinatorGuardrailBidBackend,
    CoordinatorGuardrailDetectorBackend,
    CoordinatorGuardrailProposalBackend,
    CoordinatorGuardrailRepairBackend,
    coordinator_throttle_config_from_env,
)


class _MockProposalBackendRaises:
    """Mock proposal backend that raises on generate_proposal (simulates 429/timeout)."""

    def generate_proposal(self, state_digest, allowed_actions, step_id, method_id, **kwargs):
        raise RuntimeError("simulated 429 or timeout")


class _MockProposalBackendOk:
    """Mock proposal backend that returns a valid minimal proposal."""

    def generate_proposal(self, state_digest, allowed_actions, step_id, method_id, **kwargs):
        agent_ids = [p.get("agent_id") for p in (state_digest.get("per_agent") or [])]
        if not agent_ids:
            agent_ids = ["ops_0"]
        per_agent = [{"agent_id": a, "action_type": "NOOP", "args": {}, "reason_code": "OK"} for a in sorted(agent_ids)]
        return (
            {
                "proposal_id": "ok",
                "step_id": step_id,
                "method_id": method_id,
                "per_agent": per_agent,
                "comms": [],
                "meta": {},
            },
            {"latency_ms": 1.0},
        )


class _MockBidBackendRaises:
    """Mock bid backend that raises (simulates 429/timeout)."""

    def generate_proposal(self, state_digest, step_id, method_id, **kwargs):
        raise RuntimeError("simulated 429")


class _MockRepairBackendRaises:
    """Mock repair backend that raises on repair."""

    def repair(self, repair_input, agent_ids):
        raise RuntimeError("simulated 429 or timeout")


def _digest_with_agents(agent_ids=None):
    if agent_ids is None:
        agent_ids = ["ops_0", "runner_0"]
    return {
        "per_agent": [{"agent_id": a} for a in agent_ids],
        "per_device": [],
    }


def test_coordinator_guardrail_proposal_returns_noop_on_inner_raise() -> None:
    """When inner proposal backend raises, wrapper returns NOOP proposal and records block."""
    inner = _MockProposalBackendRaises()
    wrapper = CoordinatorGuardrailProposalBackend(
        inner,
        config={
            "circuit_consecutive_threshold": 1,
            "circuit_cooldown_calls": 2,
            "rate_max_calls": 60,
            "rate_window_seconds": 60.0,
        },
    )
    digest = _digest_with_agents()
    proposal, meta = wrapper.generate_proposal(digest, ["NOOP", "TICK"], step_id=0, method_id="llm_central_planner")
    assert meta.get("reason_code") == "CIRCUIT_BREAKER_OPEN"
    assert proposal.get("per_agent")
    for pa in proposal["per_agent"]:
        assert pa.get("action_type") == "NOOP"
    assert proposal.get("meta", {}).get("reason_code") == "CIRCUIT_BREAKER_OPEN"


def test_coordinator_guardrail_proposal_circuit_opens_after_raise() -> None:
    """After inner raises once, circuit opens and next call returns CIRCUIT_BREAKER_OPEN without calling inner."""
    inner = _MockProposalBackendRaises()
    wrapper = CoordinatorGuardrailProposalBackend(
        inner,
        config={
            "circuit_consecutive_threshold": 1,
            "circuit_cooldown_calls": 3,
            "rate_max_calls": 60,
            "rate_window_seconds": 60.0,
        },
    )
    digest = _digest_with_agents()
    wrapper.generate_proposal(digest, ["NOOP"], step_id=0, method_id="test")
    proposal2, meta2 = wrapper.generate_proposal(digest, ["NOOP"], step_id=1, method_id="test")
    assert meta2.get("reason_code") == "CIRCUIT_BREAKER_OPEN"
    assert proposal2["per_agent"][0]["action_type"] == "NOOP"


def test_coordinator_guardrail_proposal_rate_limited() -> None:
    """When rate limit is exceeded, wrapper returns NOOP proposal with RATE_LIMITED."""
    inner = _MockProposalBackendOk()
    wrapper = CoordinatorGuardrailProposalBackend(
        inner,
        config={
            "circuit_consecutive_threshold": 5,
            "circuit_cooldown_calls": 10,
            "rate_max_calls": 1,
            "rate_window_seconds": 60.0,
        },
    )
    digest = _digest_with_agents()
    wrapper.generate_proposal(digest, ["NOOP"], step_id=0, method_id="test")
    proposal2, meta2 = wrapper.generate_proposal(digest, ["NOOP"], step_id=1, method_id="test")
    assert meta2.get("reason_code") == "RATE_LIMITED"
    assert proposal2["per_agent"][0]["action_type"] == "NOOP"


def test_coordinator_guardrail_bid_returns_noop_on_inner_raise() -> None:
    """When inner bid backend raises, wrapper returns NOOP bid proposal with empty market."""
    inner = _MockBidBackendRaises()
    wrapper = CoordinatorGuardrailBidBackend(
        inner,
        config={
            "circuit_consecutive_threshold": 1,
            "circuit_cooldown_calls": 2,
            "rate_max_calls": 60,
            "rate_window_seconds": 60.0,
        },
    )
    digest = _digest_with_agents()
    proposal, meta = wrapper.generate_proposal(digest, step_id=0, method_id="llm_auction_bidder")
    assert meta.get("reason_code") == "CIRCUIT_BREAKER_OPEN"
    assert proposal.get("market") == []
    assert proposal.get("per_agent")


def test_coordinator_guardrail_repair_returns_noop_on_inner_raise() -> None:
    """When inner repair backend raises, wrapper returns NOOP repair result and reason code."""
    inner = _MockRepairBackendRaises()
    wrapper = CoordinatorGuardrailRepairBackend(
        inner,
        config={
            "circuit_consecutive_threshold": 1,
            "circuit_cooldown_calls": 2,
            "rate_max_calls": 60,
            "rate_window_seconds": 60.0,
        },
    )
    agent_ids = ["ops_0", "runner_0"]
    per_agent, meta = wrapper.repair({"blocked_actions": []}, agent_ids)
    assert meta.get("reason_code") == "CIRCUIT_BREAKER_OPEN"
    assert len(per_agent) == len(agent_ids)
    for item in per_agent:
        assert item[1] == "NOOP"


def test_coordinator_guardrail_repair_circuit_opens_after_raise() -> None:
    """After repair backend raises once, next repair call returns fallback without calling inner."""
    inner = _MockRepairBackendRaises()
    wrapper = CoordinatorGuardrailRepairBackend(
        inner,
        config={
            "circuit_consecutive_threshold": 1,
            "circuit_cooldown_calls": 3,
            "rate_max_calls": 60,
            "rate_window_seconds": 60.0,
        },
    )
    agent_ids = ["ops_0"]
    wrapper.repair({}, agent_ids)
    per_agent2, meta2 = wrapper.repair({}, agent_ids)
    assert meta2.get("reason_code") == "CIRCUIT_BREAKER_OPEN"
    assert per_agent2[0][1] == "NOOP"


def test_coordinator_throttle_config_from_env() -> None:
    """coordinator_throttle_config_from_env returns a dict (may be empty when env unset)."""
    cfg = coordinator_throttle_config_from_env()
    assert isinstance(cfg, dict)


class _MockDetectorBackendRaises:
    """Mock detector backend that raises on detect (simulates 429/timeout)."""

    def detect(self, step, event_summary, comms_stats):
        raise RuntimeError("simulated 429 or timeout")


class _MockDetectorBackendOk:
    """Mock detector backend that returns a valid DetectorOutput."""

    def detect(self, step, event_summary, comms_stats):
        from labtrust_gym.baselines.coordination.assurance.detector_advisor import (
            DetectorOutput,
            DetectResult,
            RecommendResult,
        )

        return DetectorOutput(
            detect=DetectResult(
                is_attack_suspected=True,
                suspected_risk_id="INJ-TEST",
                suspect_agent_ids=[],
            ),
            recommend=RecommendResult(
                enforcement_action="throttle",
                scope="",
                rationale_short="test",
            ),
        )


def test_coordinator_guardrail_detector_returns_fallback_on_inner_raise() -> None:
    """When inner detector backend raises, wrapper returns safe fallback (no suspicion, none)."""
    inner = _MockDetectorBackendRaises()
    wrapper = CoordinatorGuardrailDetectorBackend(
        inner,
        config={
            "circuit_consecutive_threshold": 1,
            "circuit_cooldown_calls": 2,
            "rate_max_calls": 60,
            "rate_window_seconds": 60.0,
        },
    )
    out = wrapper.detect(0, {"step": 0}, None)
    assert out.detect.is_attack_suspected is False
    assert out.recommend.enforcement_action == "none"


def test_coordinator_guardrail_detector_circuit_opens_after_raise() -> None:
    """After inner raises once, next detect returns fallback without calling inner."""
    inner = _MockDetectorBackendRaises()
    wrapper = CoordinatorGuardrailDetectorBackend(
        inner,
        config={
            "circuit_consecutive_threshold": 1,
            "circuit_cooldown_calls": 3,
            "rate_max_calls": 60,
            "rate_window_seconds": 60.0,
        },
    )
    wrapper.detect(0, {}, None)
    out2 = wrapper.detect(1, {}, None)
    assert out2.detect.is_attack_suspected is False
    assert out2.recommend.enforcement_action == "none"


def test_coordinator_guardrail_detector_rate_limited() -> None:
    """When rate limit exceeded, wrapper returns fallback without calling inner."""
    inner = _MockDetectorBackendOk()
    wrapper = CoordinatorGuardrailDetectorBackend(
        inner,
        config={
            "circuit_consecutive_threshold": 5,
            "circuit_cooldown_calls": 10,
            "rate_max_calls": 1,
            "rate_window_seconds": 60.0,
        },
    )
    wrapper.detect(0, {}, None)
    out2 = wrapper.detect(1, {}, None)
    assert out2.detect.is_attack_suspected is False
    assert out2.recommend.enforcement_action == "none"


def test_coordinator_guardrail_detector_success_delegates_to_inner() -> None:
    """When circuit and rate allow, wrapper delegates to inner and returns inner output."""
    inner = _MockDetectorBackendOk()
    wrapper = CoordinatorGuardrailDetectorBackend(
        inner,
        config={
            "circuit_consecutive_threshold": 5,
            "circuit_cooldown_calls": 10,
            "rate_max_calls": 60,
            "rate_window_seconds": 60.0,
        },
    )
    out = wrapper.detect(0, {"step": 0}, {})
    assert out.detect.is_attack_suspected is True
    assert out.detect.suspected_risk_id == "INJ-TEST"
    assert out.recommend.enforcement_action == "throttle"
