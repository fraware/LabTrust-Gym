"""
LLM guardrails: circuit breaker and rate limiter (unit and integration).

Unit tests for CircuitBreaker and RateLimiter; integration test that the agent
returns CIRCUIT_BREAKER_OPEN and RATE_LIMITED when the circuit is open or rate
limit is exceeded. No real API; mocks only.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from labtrust_gym.baselines.llm.throttle import (
    CircuitBreaker,
    RateLimiter,
    throttle_config_from_env,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# --- Unit: CircuitBreaker ---


def test_circuit_breaker_opens_after_threshold() -> None:
    """After consecutive_blocks >= threshold, should_skip_llm returns True for cooldown_calls steps."""
    cb = CircuitBreaker(consecutive_threshold=2, cooldown_calls=3)
    assert cb.should_skip_llm() is False
    cb.record_block()
    assert cb.should_skip_llm() is False
    cb.record_block()
    assert cb.should_skip_llm() is True
    assert cb.should_skip_llm() is True
    assert cb.should_skip_llm() is True
    assert cb.should_skip_llm() is False


def test_circuit_breaker_resets_on_success() -> None:
    """record_success resets consecutive_blocks; circuit does not open until threshold again."""
    cb = CircuitBreaker(consecutive_threshold=2, cooldown_calls=2)
    cb.record_block()
    cb.record_success()
    cb.record_block()
    assert cb.should_skip_llm() is False
    cb.record_block()
    assert cb.should_skip_llm() is True


def test_circuit_breaker_reset_clears_state() -> None:
    """reset() clears consecutive_blocks and cooldown_remaining."""
    cb = CircuitBreaker(consecutive_threshold=1, cooldown_calls=2)
    cb.record_block()
    assert cb.should_skip_llm() is True
    cb.reset()
    assert cb.should_skip_llm() is False


# --- Unit: RateLimiter ---


def test_rate_limiter_allows_until_max() -> None:
    """allow_call returns True until max_calls reached; record_call adds to window."""
    rl = RateLimiter(max_calls=2, window_seconds=60.0)
    assert rl.allow_call() is True
    rl.record_call()
    assert rl.allow_call() is True
    rl.record_call()
    assert rl.allow_call() is False


def test_rate_limiter_reset_clears_history() -> None:
    """reset() clears call history so allow_call becomes True again."""
    rl = RateLimiter(max_calls=1, window_seconds=60.0)
    rl.record_call()
    assert rl.allow_call() is False
    rl.reset()
    assert rl.allow_call() is True


# --- Unit: throttle_config_from_env ---


def test_throttle_config_from_env_reads_vars() -> None:
    """throttle_config_from_env reads LABTRUST_* env vars when set."""
    with patch.dict(
        os.environ,
        {
            "LABTRUST_CIRCUIT_BREAKER_THRESHOLD": "2",
            "LABTRUST_CIRCUIT_BREAKER_COOLDOWN": "5",
            "LABTRUST_RATE_LIMIT_MAX_CALLS": "10",
            "LABTRUST_RATE_LIMIT_WINDOW_SECONDS": "30",
        },
        clear=False,
    ):
        cfg = throttle_config_from_env()
    assert cfg.get("circuit_consecutive_threshold") == 2
    assert cfg.get("circuit_cooldown_calls") == 5
    assert cfg.get("rate_max_calls") == 10
    assert cfg.get("rate_window_seconds") == 30.0


# --- Integration: agent returns CIRCUIT_BREAKER_OPEN when circuit is open ---


def test_agent_returns_circuit_breaker_open_when_circuit_open() -> None:
    """When pipeline_mode is llm_live and circuit is open, act() returns NOOP with CIRCUIT_BREAKER_OPEN."""
    from labtrust_gym.baselines.llm.agent import (
        LLMAgentWithShield,
        MockDeterministicBackendV2,
    )
    from labtrust_gym.engine.rbac import (
        get_agent_role,
        get_allowed_actions,
        load_rbac_policy,
    )
    from labtrust_gym.pipeline import set_pipeline_config

    rbac_path = _repo_root() / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
    if not rbac_path.exists():
        pytest.skip("rbac_policy.v0.1.yaml not found")
    rbac_policy = load_rbac_policy(rbac_path)
    backend = MockDeterministicBackendV2(default_action_type="NOOP")
    pz_to_engine = {"ops_0": "A_OPS_0"}
    try:
        set_pipeline_config("llm_live", allow_network=True)
        agent = LLMAgentWithShield(
            backend=backend,
            rbac_policy=rbac_policy,
            pz_to_engine=pz_to_engine,
            schema_path=_repo_root() / "policy/llm/llm_action.schema.v0.2.json",
            strict_signatures=False,
            use_action_proposal_schema=True,
        )
        cb = CircuitBreaker(consecutive_threshold=1, cooldown_calls=2)
        cb.record_block()
        agent._circuit_breaker = cb
        obs = {
            "zone_id": "Z_SRA_RECEPTION",
            "site_id": "SITE_HUB",
            "queue_by_device": [],
            "log_frozen": 0,
            "t_s": 0,
            "my_zone_idx": 1,
        }
        action_idx, action_info, meta = agent.act(obs, "ops_0")
        assert meta.get("_shield_filtered") is True
        assert meta.get("_shield_reason_code") == "CIRCUIT_BREAKER_OPEN"
        assert action_info.get("action_type") == "NOOP"
    finally:
        set_pipeline_config("deterministic", allow_network=False)


def test_agent_returns_rate_limited_when_over_limit() -> None:
    """When pipeline_mode is llm_live and rate limiter is at limit, act() returns NOOP with RATE_LIMITED."""
    import hashlib
    import json

    from labtrust_gym.baselines.llm.agent import (
        LLMAgentWithShield,
        MockDeterministicBackendV2,
        _obs_hash,
    )
    from labtrust_gym.baselines.llm.shield import build_policy_summary
    from labtrust_gym.engine.rbac import (
        get_agent_role,
        get_allowed_actions,
        load_rbac_policy,
    )
    from labtrust_gym.pipeline import set_pipeline_config

    rbac_path = _repo_root() / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
    if not rbac_path.exists():
        pytest.skip("rbac_policy.v0.1.yaml not found")
    rbac_policy = load_rbac_policy(rbac_path)
    obs = {
        "zone_id": "Z_SRA_RECEPTION",
        "site_id": "SITE_HUB",
        "queue_by_device": [],
        "log_frozen": 0,
        "t_s": 0,
        "my_zone_idx": 1,
    }
    engine_id = "A_OPS_0"
    allowed = get_allowed_actions(engine_id, rbac_policy)
    role_id = get_agent_role(engine_id, rbac_policy)
    policy_summary = build_policy_summary(allowed_actions=allowed, role_id=role_id)
    citation_anchors = list(policy_summary.get("citation_anchors") or [])
    user_content = json.dumps(
        {
            "obs_hash": _obs_hash(obs),
            "allowed_actions": allowed,
            "citation_anchors": citation_anchors,
        },
        sort_keys=True,
    )
    key = hashlib.sha256(user_content.encode()).hexdigest()[:16]
    canned = {key: {"action_type": "TICK", "args": {}, "rationale": "ok"}}
    backend = MockDeterministicBackendV2(canned=canned, default_action_type="NOOP")
    pz_to_engine = {"ops_0": "A_OPS_0"}
    rl = RateLimiter(max_calls=1, window_seconds=60.0)
    rl.record_call()
    try:
        set_pipeline_config("llm_live", allow_network=True)
        agent = LLMAgentWithShield(
            backend=backend,
            rbac_policy=rbac_policy,
            pz_to_engine=pz_to_engine,
            schema_path=_repo_root() / "policy/llm/llm_action.schema.v0.2.json",
            strict_signatures=False,
            use_action_proposal_schema=True,
        )
        agent._rate_limiter = rl
        action_idx, action_info, meta = agent.act(obs, "ops_0")
        assert meta.get("_shield_filtered") is True
        assert meta.get("_shield_reason_code") == "RATE_LIMITED"
        assert action_info.get("action_type") == "NOOP"
    finally:
        set_pipeline_config("deterministic", allow_network=False)
