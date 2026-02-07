"""
Smoke test: run TaskG_COORD_SCALE with small scale (10 agents) for 1 episode.

Ensures no crash; env resets and steps with scale-generated initial_state.
Coordination smoke: TaskG with deterministic kernel method, TaskH with one injection;
named scale preset (small_smoke); results schema validity and non-empty coordination metrics.
"""

import tempfile
from pathlib import Path

from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
from labtrust_gym.benchmarks.runner import run_benchmark
from labtrust_gym.benchmarks.summarize import validate_results_v02
from labtrust_gym.benchmarks.tasks import get_task


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_taskg_coord_scale_one_episode_smoke() -> None:
    """Run TaskG_COORD_SCALE with 1 episode, seed 42; must complete without crash."""
    root = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results.json"
        results = run_benchmark(
            task_name="TaskG_COORD_SCALE",
            num_episodes=1,
            base_seed=42,
            out_path=out,
            repo_root=root,
        )
        assert results is not None
        assert results.get("task") == "TaskG_COORD_SCALE"
        assert results.get("num_episodes") == 1
        assert len(results.get("episodes", [])) == 1
        ep = results["episodes"][0]
        assert "seed" in ep
        assert "metrics" in ep
        assert out.exists()


def test_taskg_task_exists_and_has_scale_config() -> None:
    """TaskG_COORD_SCALE exists and has scale_config set."""
    task = get_task("TaskG_COORD_SCALE")
    assert task.name == "TaskG_COORD_SCALE"
    assert task.scale_config is not None
    assert task.scale_config.num_agents_total == 10
    initial = task.get_initial_state(42)
    assert len(initial["agents"]) == 10
    assert initial["agents"][0]["agent_id"] == "A_WORKER_0001"


def test_taskg_llm_hierarchical_allocator_deterministic_smoke() -> None:
    """TaskG with llm_hierarchical_allocator and deterministic backend completes without crash."""
    root = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results_hier.json"
        results = run_benchmark(
            task_name="TaskG_COORD_SCALE",
            num_episodes=1,
            base_seed=43,
            out_path=out,
            repo_root=root,
            coord_method="llm_hierarchical_allocator",
            llm_backend=None,
        )
        assert results is not None
        assert results.get("task") == "TaskG_COORD_SCALE"
        assert len(results.get("episodes", [])) == 1


def test_taskg_llm_auction_bidder_deterministic_smoke() -> None:
    """TaskG with llm_auction_bidder and deterministic backend completes without crash."""
    root = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results_auction.json"
        results = run_benchmark(
            task_name="TaskG_COORD_SCALE",
            num_episodes=1,
            base_seed=44,
            out_path=out,
            repo_root=root,
            coord_method="llm_auction_bidder",
            llm_backend=None,
        )
        assert results is not None
        assert results.get("task") == "TaskG_COORD_SCALE"
        assert len(results.get("episodes", [])) == 1


def test_load_scale_config_by_id_medium_stress_signed_bus() -> None:
    """Named preset medium_stress_signed_bus loads and has expected shape."""
    root = _repo_root()
    scale = load_scale_config_by_id(root, "medium_stress_signed_bus")
    assert scale.num_agents_total == 75
    assert 8 <= sum(scale.num_devices_per_type.values()) <= 12
    assert scale.num_sites == 2
    assert 200 <= scale.horizon_steps <= 400
    assert scale.timing_mode in ("explicit", "simulated")


def test_coordination_smoke_taskg_taskh_named_scale_and_metrics(tmp_path: Path) -> None:
    """
    TaskG with deterministic kernel method and TaskH with INJ-COMMS-POISON-001,
    using named scale preset (small_smoke). Asserts results schema validity and
    non-empty coordination metrics.
    """
    root = _repo_root()
    scale_config = load_scale_config_by_id(root, "small_smoke")
    out_g = tmp_path / "taskg_results.json"
    out_h = tmp_path / "taskh_results.json"

    results_g = run_benchmark(
        task_name="TaskG_COORD_SCALE",
        num_episodes=1,
        base_seed=100,
        out_path=out_g,
        repo_root=root,
        coord_method="centralized_planner",
        scale_config_override=scale_config,
    )
    errors_g = validate_results_v02(results_g)
    assert not errors_g, f"TaskG results invalid: {errors_g}"
    assert results_g.get("task") == "TaskG_COORD_SCALE"
    episodes_g = results_g.get("episodes") or []
    assert len(episodes_g) == 1
    metrics_g = episodes_g[0].get("metrics") or {}
    coord_g = metrics_g.get("coordination") or {}
    assert coord_g, "TaskG with coord_method must produce non-empty coordination metrics"

    results_h = run_benchmark(
        task_name="TaskH_COORD_RISK",
        num_episodes=1,
        base_seed=101,
        out_path=out_h,
        repo_root=root,
        coord_method="kernel_auction_whca_shielded",
        injection_id="INJ-COMMS-POISON-001",
        scale_config_override=scale_config,
    )
    errors_h = validate_results_v02(results_h)
    assert not errors_h, f"TaskH results invalid: {errors_h}"
    assert results_h.get("task") == "TaskH_COORD_RISK"
    episodes_h = results_h.get("episodes") or []
    assert len(episodes_h) == 1
    metrics_h = episodes_h[0].get("metrics") or {}
    coord_h = metrics_h.get("coordination") or {}
    assert coord_h, "TaskH with coord_method must produce non-empty coordination metrics"
