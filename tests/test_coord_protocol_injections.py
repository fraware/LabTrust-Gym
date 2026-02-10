"""
Unit and integration tests for LLM coordination protocol-targeted injections:
INJ-COORD-PROMPT-INJECT-001, INJ-COORD-PLAN-REPLAY-001, INJ-COORD-BID-SHILL-001.
Deterministic, auditable; mapped to risk_registry and method_risk_matrix.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from labtrust_gym.security.risk_injections import make_injector

COORD_PROTOCOL_INJECTION_IDS = [
    "INJ-COORD-PROMPT-INJECT-001",
    "INJ-COORD-PLAN-REPLAY-001",
    "INJ-COORD-BID-SHILL-001",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _signature_coord_protocol(
    seed: int,
    injection_id: str,
    steps: int = 20,
    intensity: float = 0.8,
    seed_offset: int = 0,
) -> str:
    """Deterministic signature of mutation pattern for coord protocol injections."""
    inj = make_injector(injection_id, intensity=intensity, seed_offset=seed_offset)
    inj.reset(seed, None)
    obs = {
        "ops_0": {"queue_has_head": [0, 1], "zone_id": "Z_A"},
        "runner_0": {"zone_id": "Z_B"},
        "runner_1": {"zone_id": "Z_A"},
    }
    actions_dict = {
        "ops_0": {"action_index": 5, "action_type": "START_RUN", "args": {}},
        "runner_0": {"action_index": 5},
        "runner_1": {"action_index": 3},
    }
    recs = []
    for _ in range(steps):
        obs, audit_obs = inj.mutate_obs(obs)
        actions_dict, audit_actions = inj.mutate_actions(actions_dict)
        rec = {"audit_obs": audit_obs is not None, "audit_actions": len(audit_actions)}
        if audit_obs:
            rec["injection_id"] = audit_obs.get("injection_id")
        for aid, ad in actions_dict.items():
            if ad.get("_coord_context_poison") or ad.get("_replay_plan_id") or ad.get("_shill_bid_bias") is not None:
                rec["mut"] = (aid, [k for k in ad if k.startswith("_")])
                break
        recs.append(json.dumps(rec, sort_keys=True))
        inj.observe_step([])
    return hashlib.sha256("\n".join(recs).encode()).hexdigest()


@pytest.mark.parametrize("injection_id", COORD_PROTOCOL_INJECTION_IDS)
def test_coord_protocol_injection_deterministic_seed(injection_id: str) -> None:
    """Same seed produces identical mutation sequence for each coord protocol injection."""
    seed = 7777
    h1 = _signature_coord_protocol(seed, injection_id)
    h2 = _signature_coord_protocol(seed, injection_id)
    assert h1 == h2, f"{injection_id}: same seed must yield same sequence hash"


@pytest.mark.parametrize("injection_id", COORD_PROTOCOL_INJECTION_IDS)
def test_coord_protocol_injection_make_and_reset(injection_id: str) -> None:
    """Each coord protocol injection_id is known and resets without error."""
    inj = make_injector(injection_id, intensity=0.5, seed_offset=2)
    assert inj.injection_id == injection_id
    inj.reset(100, None)
    assert inj._step == 0


def test_coord_prompt_inject_001_applies_at_deterministic_step() -> None:
    """INJ-COORD-PROMPT-INJECT-001 applies at a step determined by seed."""
    inj = make_injector("INJ-COORD-PROMPT-INJECT-001", intensity=1.0, seed_offset=0)
    inj.reset(13, None)
    obs = {"ops_0": {"zone_id": "Z_A"}, "runner_0": {"zone_id": "Z_B"}}
    applied_step = None
    for step in range(25):
        obs, audit = inj.mutate_obs(obs)
        if audit is not None or any("_coord_context_poison" in str(o) for o in obs.values()):
            applied_step = step
            break
        inj.observe_step([])
    assert applied_step is not None, "Injection must apply within 25 steps"
    inj2 = make_injector("INJ-COORD-PROMPT-INJECT-001", intensity=1.0, seed_offset=0)
    inj2.reset(13, None)
    obs2 = {"ops_0": {"zone_id": "Z_A"}, "runner_0": {"zone_id": "Z_B"}}
    for step in range(25):
        obs2, audit2 = inj2.mutate_obs(obs2)
        if audit2 is not None:
            assert step == applied_step, "Same seed => same apply step"
            break
        inj2.observe_step([])


def test_plan_replay_001_replays_with_stale_epoch_marker() -> None:
    """INJ-COORD-PLAN-REPLAY-001 replay carries _replay_plan_id and _stale_epoch."""
    inj = make_injector("INJ-COORD-PLAN-REPLAY-001", intensity=1.0, seed_offset=0)
    inj.reset(42, None)
    actions = {
        "ops_0": {"action_index": 5, "action_type": "START_RUN"},
        "runner_0": {"action_index": 3},
    }
    seen_replay = False
    for _ in range(30):
        out, audits = inj.mutate_actions(actions)
        for ad in out.values():
            if ad.get("_stale_epoch") and ad.get("_replay_plan_id"):
                seen_replay = True
                break
        if seen_replay:
            break
        inj.observe_step([])
    assert seen_replay, "Plan replay must inject replayed action with stale markers within 30 steps"


def test_bid_shill_001_applies_shill_bias() -> None:
    """INJ-COORD-BID-SHILL-001 mutate_actions yields _shill_bid_bias on subset of agents."""
    inj = make_injector("INJ-COORD-BID-SHILL-001", intensity=1.0, seed_offset=0)
    inj.reset(99, None)
    actions = {
        "ops_0": {"action_index": 5},
        "runner_0": {"action_index": 5},
    }
    found = False
    for _ in range(25):
        out, audits = inj.mutate_actions(actions)
        for ad in out.values():
            if ad.get("_shill_bid_bias") is not None:
                found = True
                assert ad["_shill_bid_bias"] == 100
                break
        if found:
            break
        inj.observe_step([])
    assert found, "Bid shill must apply within 25 steps"


# --- Integration: TaskH produces non-null sec metrics ---


def _run_taskh_one_episode(
    tmp_path: Path,
    injection_id: str,
    coord_method: str = "kernel_auction_whca_shielded",
    seed: int = 100,
) -> dict:
    from labtrust_gym.benchmarks.runner import run_benchmark

    out = tmp_path / "results.json"
    run_benchmark(
        task_name="coord_risk",
        num_episodes=1,
        base_seed=seed,
        out_path=out,
        repo_root=_repo_root(),
        coord_method=coord_method,
        injection_id=injection_id,
        pipeline_mode="deterministic",
    )
    assert out.exists()
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.mark.parametrize("injection_id", COORD_PROTOCOL_INJECTION_IDS)
def test_taskh_coord_protocol_injection_produces_sec_metrics(
    tmp_path: Path, injection_id: str
) -> None:
    """TaskH run with each coord protocol injection produces non-null sec block and expected keys."""
    data = _run_taskh_one_episode(tmp_path, injection_id)
    episodes = data.get("episodes") or []
    assert len(episodes) >= 1
    metrics = episodes[0].get("metrics") or {}
    sec = metrics.get("sec")
    assert sec is not None, f"{injection_id}: metrics.sec must be present"
    assert "attack_success_rate" in sec
    assert "stealth_success_rate" in sec
    assert "blast_radius_proxy" in sec
    assert sec.get("injection_id") == injection_id
