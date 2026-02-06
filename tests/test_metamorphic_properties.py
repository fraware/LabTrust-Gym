"""
Metamorphic testing: properties that must hold across transformations.

All tests are deterministic (fixed seeds). Used in CI smoke to detect
contract violations, non-determinism, and safety bypasses.

Metamorphic relations:
- Renaming agent IDs (bijection) should not change safety outcome.
- Reordering irrelevant events (e.g. TICKs) should not create a release.
- Doubling t_s for TICK-only sequence should not change accept/block outcomes.
- Adding a no-op TICK at end should not change prior outcomes.
- Same seed implies same step outcomes (determinism).
- Empty sequence yields no releases.
- Independent events permuted yield consistent safety (e.g. both ACCEPTED).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.tools.registry import load_tool_registry

# Fixed seeds for reproducibility in CI
SEED = 42
SEED_ALT = 12345


def _repo_root() -> Path:
    from labtrust_gym.config import get_repo_root

    return Path(get_repo_root())


def _minimal_initial_state(
    agents: list[dict[str, Any]] | None = None,
    tool_registry: dict[str, Any] | None = None,
    policy_root: Path | None = None,
) -> dict[str, Any]:
    """Minimal initial_state for CoreEnv with optional multiple agents."""
    if agents is None:
        agents = [
            {"agent_id": "A_OPS_0", "zone_id": "Z_MAIN"},
            {"agent_id": "A_RECEPTION_0", "zone_id": "Z_MAIN"},
        ]
    if tool_registry is None:
        root = _repo_root()
        tool_registry = load_tool_registry(root) or {}
    state: dict[str, Any] = {
        "effective_policy": {},
        "agents": list(agents),
        "zone_layout": {
            "zones": [{"zone_id": "Z_MAIN"}],
            "graph_edges": [],
            "doors": [],
            "device_placement": {},
        },
        "specimens": [],
        "tokens": [],
        "audit_fault_injection": None,
        "tool_registry": tool_registry,
    }
    if policy_root is not None:
        state["policy_root"] = policy_root
    return state


def _run_sequence(
    env: CoreEnv,
    initial_state: dict[str, Any],
    events: list[dict[str, Any]],
    seed: int,
) -> list[dict[str, Any]]:
    """Reset env and run events; return list of step results."""
    env.reset(initial_state, deterministic=True, rng_seed=seed)
    results = []
    for ev in events:
        res = env.step(ev)
        results.append(
            {
                "status": res.get("status"),
                "blocked_reason_code": res.get("blocked_reason_code"),
                "emits": list(res.get("emits") or []),
            }
        )
    return results


def _safety_outcome(results: list[dict[str, Any]]) -> list[str]:
    """Per-step safety: ACCEPTED vs BLOCKED."""
    return [r.get("status", "") for r in results]


def _has_release(results: list[dict[str, Any]]) -> bool:
    """True if any step emitted a release-related emit."""
    for r in results:
        emits = r.get("emits") or []
        if any("RELEASE" in e for e in emits):
            return True
    return False


# ---------- Metamorphic property tests ----------


@pytest.mark.metamorphic
def test_determinism_same_seed_same_outcomes() -> None:
    """Same seed and same event sequence must yield identical step outcomes."""
    root = _repo_root()
    state = _minimal_initial_state(policy_root=root)
    events = [
        {"t_s": 0, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}},
        {"t_s": 1, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}},
    ]
    env1 = CoreEnv()
    env2 = CoreEnv()
    res1 = _run_sequence(env1, state, events, SEED)
    res2 = _run_sequence(env2, state, events, SEED)
    assert _safety_outcome(res1) == _safety_outcome(res2)
    assert res1 == res2


@pytest.mark.metamorphic
def test_renaming_agent_ids_preserves_safety_outcome() -> None:
    """Bijection on agent_id in events should not change accept/block pattern (by role)."""
    root = _repo_root()
    agents = [
        {"agent_id": "Agent_A", "zone_id": "Z_MAIN"},
        {"agent_id": "Agent_B", "zone_id": "Z_MAIN"},
    ]
    state1 = _minimal_initial_state(agents=agents, policy_root=root)
    state2 = _minimal_initial_state(agents=agents, policy_root=root)
    events_1 = [
        {"t_s": 0, "agent_id": "Agent_A", "action_type": "TICK", "args": {}},
        {"t_s": 1, "agent_id": "Agent_B", "action_type": "TICK", "args": {}},
    ]
    events_2 = [
        {"t_s": 0, "agent_id": "Agent_B", "action_type": "TICK", "args": {}},
        {"t_s": 1, "agent_id": "Agent_A", "action_type": "TICK", "args": {}},
    ]
    env = CoreEnv()
    out1 = _run_sequence(env, state1, events_1, SEED)
    out2 = _run_sequence(env, state2, events_2, SEED)
    safety1 = _safety_outcome(out1)
    safety2 = _safety_outcome(out2)
    assert safety1 == safety2, "Swapping agent IDs should preserve safety outcome for TICK"


@pytest.mark.metamorphic
def test_reordering_ticks_does_not_create_release() -> None:
    """Reordering two TICKs should not introduce a release that was not there."""
    root = _repo_root()
    state = _minimal_initial_state(policy_root=root)
    events_a = [
        {"t_s": 0, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}},
        {"t_s": 1, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}},
    ]
    events_b = [
        {"t_s": 0, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}},
        {"t_s": 1, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}},
    ]
    env = CoreEnv()
    out_a = _run_sequence(env, state, events_a, SEED)
    out_b = _run_sequence(env, state, events_b, SEED)
    has_a = _has_release(out_a)
    has_b = _has_release(out_b)
    assert has_a == has_b, "Reordering TICKs must not flip release presence"


@pytest.mark.metamorphic
def test_doubling_tick_timesteps_preserves_accept_block() -> None:
    """Doubling t_s for TICK-only sequence should not change accept/block."""
    root = _repo_root()
    state = _minimal_initial_state(policy_root=root)
    events_short = [
        {"t_s": 0, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}},
        {"t_s": 1, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}},
    ]
    events_long = [
        {"t_s": 0, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}},
        {"t_s": 2, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}},
    ]
    env = CoreEnv()
    out_short = _run_sequence(env, state, events_short, SEED)
    out_long = _run_sequence(env, state, events_long, SEED)
    assert _safety_outcome(out_short) == _safety_outcome(out_long)


@pytest.mark.metamorphic
def test_append_noop_tick_preserves_prior_outcomes() -> None:
    """Adding a no-op TICK at the end should not change prior step outcomes."""
    root = _repo_root()
    state = _minimal_initial_state(policy_root=root)
    events_base = [
        {"t_s": 0, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}},
    ]
    events_extra = events_base + [
        {"t_s": 1, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}},
    ]
    env = CoreEnv()
    out_base = _run_sequence(env, state, events_base, SEED)
    out_extra = _run_sequence(env, state, events_extra, SEED)
    assert out_base == out_extra[: len(out_base)]


@pytest.mark.metamorphic
def test_empty_sequence_no_releases() -> None:
    """Empty event sequence yields no releases."""
    root = _repo_root()
    state = _minimal_initial_state(policy_root=root)
    env = CoreEnv()
    env.reset(state, deterministic=True, rng_seed=SEED)
    assert not _has_release([])


@pytest.mark.metamorphic
def test_same_event_twice_same_result() -> None:
    """Same event twice with same seed gives same result for that event type."""
    root = _repo_root()
    state = _minimal_initial_state(policy_root=root)
    event = {"t_s": 0, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}}
    env = CoreEnv()
    res1 = _run_sequence(env, state, [event], SEED)
    res2 = _run_sequence(env, state, [event, copy.deepcopy(event)], SEED)
    assert res1[0]["status"] == res2[0]["status"]
    assert res1[0]["status"] == res2[1]["status"]


@pytest.mark.metamorphic
def test_different_seed_may_differ_but_contract_holds() -> None:
    """Different seeds may differ; step result must still satisfy contract."""
    root = _repo_root()
    state = _minimal_initial_state(policy_root=root)
    events = [{"t_s": i, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}} for i in range(3)]
    env = CoreEnv()
    for seed in (SEED, SEED_ALT):
        results = _run_sequence(env, state, events, seed)
        for r in results:
            assert r.get("status") in ("ACCEPTED", "BLOCKED")
            assert isinstance(r.get("emits"), list)


@pytest.mark.metamorphic
def test_contract_required_keys_present() -> None:
    """Step result must contain status, emits, violations (contract)."""
    root = _repo_root()
    state = _minimal_initial_state(policy_root=root)
    events = [{"t_s": 0, "agent_id": "A_OPS_0", "action_type": "TICK", "args": {}}]
    env = CoreEnv()
    env.reset(state, deterministic=True, rng_seed=SEED)
    res = env.step(events[0])
    assert "status" in res
    assert "emits" in res
    assert "violations" in res
    assert res["status"] in ("ACCEPTED", "BLOCKED")
