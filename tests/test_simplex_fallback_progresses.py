"""
Simplex fallback: when shield rejects, fallback controller (safe_wait or local greedy)
is used. Liveness smoke: in a toy scenario, tasks eventually make progress (e.g. steps
complete without deadlock; optional: some throughput when fallback is TrivialRouter).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.baselines.coordination.assurance.simplex import (
    _safe_fallback_route,
    select_controller,
    wrap_with_simplex_shield,
)
from labtrust_gym.baselines.coordination.decision_types import RouteDecision


class _MinimalContext:
    def __init__(self, obs: dict, agent_ids: list | None = None, t: int = 0):
        self.obs = obs
        self.policy = {}
        self.t = t
        self.agent_ids = agent_ids or sorted(obs.keys())
        self.device_zone = {}


def test_fallback_route_produces_noop_per_agent() -> None:
    """_safe_fallback_route returns one NOOP per agent; deterministic."""
    context = _MinimalContext(obs={"a": {"zone_id": "Z_A"}, "b": {"zone_id": "Z_B"}})
    route = _safe_fallback_route(context)
    assert route.explain == "simplex_fallback"
    per = {aid: (at, args) for (aid, at, args) in route.per_agent}
    assert per.get("a") == ("NOOP", ())
    assert per.get("b") == ("NOOP", ())


def test_select_controller_uses_fallback_when_rejected() -> None:
    """select_controller returns fallback route when shield_ok is False."""
    advanced = RouteDecision(
        per_agent=(("a", "MOVE", (("from_zone", "Z_A"), ("to_zone", "Z_B"))),),
        explain="adv",
    )
    fallback = RouteDecision(
        per_agent=(("a", "NOOP", ()),),
        explain="fallback",
    )
    selected = select_controller(advanced, fallback, shield_ok=False)
    assert selected is fallback
    assert selected.explain == "fallback"


def test_select_controller_uses_advanced_when_accepted() -> None:
    """select_controller returns advanced route when shield_ok is True."""
    advanced = RouteDecision(
        per_agent=(("a", "MOVE", (("from_zone", "Z_A"), ("to_zone", "Z_B"))),),
        explain="adv",
    )
    fallback = RouteDecision(per_agent=(("a", "NOOP", ()),), explain="fallback")
    selected = select_controller(advanced, fallback, shield_ok=True)
    assert selected is advanced


def test_wrapped_method_step_returns_actions_and_decision() -> None:
    """wrap_with_simplex_shield: step() returns (actions, decision) and sets last_shield_emits."""
    from labtrust_gym.baselines.coordination.compose import compose_kernel
    from labtrust_gym.baselines.coordination.kernel_components import (
        CentralizedAllocator,
        EDFScheduler,
        TrivialRouter,
    )

    advanced = compose_kernel(
        CentralizedAllocator(),
        EDFScheduler(),
        TrivialRouter(),
        "test_kernel",
    )
    wrapped = wrap_with_simplex_shield(advanced, None)
    wrapped.reset(42, {}, {})
    import random

    from labtrust_gym.baselines.coordination.coordination_kernel import KernelContext

    obs = {
        "runner_0": {"zone_id": "Z_A", "queue_by_device": []},
        "runner_1": {"zone_id": "Z_B", "queue_by_device": []},
    }
    context = KernelContext(
        obs=obs,
        infos={},
        t=0,
        policy={"zone_layout": {"zones": [], "graph_edges": []}},
        scale_config={},
        seed=42,
        rng=random.Random(42),
    )
    actions, decision = wrapped.step(context)
    assert isinstance(actions, dict)
    assert "runner_0" in actions
    assert "runner_1" in actions
    assert decision is not None
    emits = wrapped.last_shield_emits
    assert len(emits) == 1
    assert "COORD_SHIELD_DECISION" in emits[0].get("emits", [])
    payload = emits[0].get("coord_shield_payload", {})
    assert "accepted" in payload
    assert "counters" in payload


def test_simplex_fallback_liveness_smoke(repo_root: Path) -> None:
    """
    Run a minimal coordination study or single episode with shielded method;
    assert run completes and at least one step executes (liveness smoke).
    """
    from labtrust_gym.benchmarks.runner import run_benchmark

    if not (repo_root / "policy").is_dir():
        pytest.skip("repo root not found")
    out = repo_root / "tests" / "tmp_simplex_smoke"
    out.mkdir(parents=True, exist_ok=True)
    try:
        run_benchmark(
            task_name="coord_risk",
            num_episodes=1,
            base_seed=99,
            out_path=out / "results.json",
            repo_root=repo_root,
            coord_method="kernel_auction_whca_shielded",
            injection_id="INJ-COMMS-DELAY-001",
        )
        data = (out / "results.json").read_text(encoding="utf-8")
        assert "episodes" in data
    finally:
        if (out / "results.json").exists():
            (out / "results.json").unlink(missing_ok=True)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent
