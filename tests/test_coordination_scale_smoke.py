"""
Smoke test: run TaskG_COORD_SCALE with small scale (10 agents) for 1 episode.

Ensures no crash; env resets and steps with scale-generated initial_state.
"""

import tempfile
from pathlib import Path

from labtrust_gym.benchmarks.runner import run_benchmark
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
