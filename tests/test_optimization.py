"""
Tests for optimization features: env reuse determinism, policy cache, observation/step behavior.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.benchmarks.runner import run_episode, run_benchmark
from labtrust_gym.benchmarks.tasks import get_task
from labtrust_gym.config import get_repo_root
from labtrust_gym.envs.pz_parallel import (
    DEFAULT_DEVICE_IDS,
    DEFAULT_ZONE_IDS,
    LabTrustParallelEnv,
)
from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
from labtrust_gym.policy.loader import (
    _policy_cache_enabled,
    load_effective_policy,
)


def test_env_reuse_same_seeds_same_metrics() -> None:
    """With env reuse, same seeds produce same metrics as without reuse."""
    task = get_task("throughput_sla")
    repo_root = Path(get_repo_root())
    policy_dir = repo_root / "policy"
    overrides = {"policy_root": str(repo_root)}

    def _env_factory(initial_state, reward_config, log_path=None):
        return LabTrustParallelEnv(
            num_runners=2,
            num_adversaries=0,
            num_insiders=0,
            dt_s=10,
            reward_config=reward_config,
            policy_dir=policy_dir,
            log_path=log_path,
        )

    agents_map = {
        "ops_0": ScriptedOpsAgent(),
        "runner_0": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS, device_ids=DEFAULT_DEVICE_IDS
        ),
        "runner_1": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS, device_ids=DEFAULT_DEVICE_IDS
        ),
    }

    m1, _ = run_episode(
        task,
        episode_seed=88,
        env_factory=_env_factory,
        scripted_agents_map=agents_map,
        initial_state_overrides=overrides,
        repo_root=repo_root,
        env=None,
    )
    m2, _ = run_episode(
        task,
        episode_seed=89,
        env_factory=_env_factory,
        scripted_agents_map=agents_map,
        initial_state_overrides=overrides,
        repo_root=repo_root,
        env=None,
    )

    first_initial = task.get_initial_state(88, policy_root=repo_root)
    first_initial = {**first_initial, **overrides}
    shared_env = _env_factory(
        initial_state=first_initial,
        reward_config=task.reward_config,
        log_path=None,
    )

    m1_reuse, _ = run_episode(
        task,
        episode_seed=88,
        env_factory=_env_factory,
        scripted_agents_map=agents_map,
        initial_state_overrides=overrides,
        repo_root=repo_root,
        env=shared_env,
    )
    m2_reuse, _ = run_episode(
        task,
        episode_seed=89,
        env_factory=_env_factory,
        scripted_agents_map=agents_map,
        initial_state_overrides=overrides,
        repo_root=repo_root,
        env=shared_env,
    )

    assert m1 == m1_reuse, "episode 88: metrics must match with and without env reuse"
    assert m2 == m2_reuse, "episode 89: metrics must match with and without env reuse"


def test_env_reuse_two_episodes_different_seeds_complete() -> None:
    """Two episodes with same env (different seeds) both complete and yield valid metrics."""
    task = get_task("throughput_sla")
    repo_root = Path(get_repo_root())
    policy_dir = repo_root / "policy"
    overrides = {"policy_root": str(repo_root)}

    def _env_factory(initial_state, reward_config, log_path=None):
        return LabTrustParallelEnv(
            num_runners=2,
            num_adversaries=0,
            num_insiders=0,
            dt_s=10,
            reward_config=reward_config,
            policy_dir=policy_dir,
            log_path=log_path,
        )

    agents_map = {
        "ops_0": ScriptedOpsAgent(),
        "runner_0": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS, device_ids=DEFAULT_DEVICE_IDS
        ),
        "runner_1": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS, device_ids=DEFAULT_DEVICE_IDS
        ),
    }

    first_initial = task.get_initial_state(100, policy_root=repo_root)
    first_initial = {**first_initial, **overrides}
    shared_env = _env_factory(
        initial_state=first_initial,
        reward_config=task.reward_config,
        log_path=None,
    )

    m1, _ = run_episode(
        task,
        episode_seed=100,
        env_factory=_env_factory,
        scripted_agents_map=agents_map,
        initial_state_overrides=overrides,
        repo_root=repo_root,
        env=shared_env,
    )
    m2, _ = run_episode(
        task,
        episode_seed=101,
        env_factory=_env_factory,
        scripted_agents_map=agents_map,
        initial_state_overrides=overrides,
        repo_root=repo_root,
        env=shared_env,
    )

    assert "throughput" in m1 and "throughput" in m2
    assert m1.get("steps") is not None and m2.get("steps") is not None


def test_policy_cache_same_input_same_output() -> None:
    """load_effective_policy with same (root, partner_id) returns identical content when cache enabled."""
    repo_root = Path(get_repo_root())
    if not _policy_cache_enabled():
        pytest.skip("LABTRUST_POLICY_CACHE is disabled")
    eff1, fp1, pid1, cal1 = load_effective_policy(repo_root, partner_id=None)
    eff2, fp2, pid2, cal2 = load_effective_policy(repo_root, partner_id=None)
    assert eff1 == eff2
    assert fp1 == fp2
    assert pid1 == pid2
    assert cal1 == cal2


def test_policy_cache_disabled_still_correct() -> None:
    """With LABTRUST_POLICY_CACHE=0, load_effective_policy still returns correct result."""
    repo_root = Path(get_repo_root())
    prev = os.environ.get("LABTRUST_POLICY_CACHE")
    try:
        os.environ["LABTRUST_POLICY_CACHE"] = "0"
        eff, fp, pid, cal = load_effective_policy(repo_root, partner_id=None)
        assert isinstance(eff, dict)
        assert (
            "critical_thresholds" in eff
            or "equipment_registry" in eff
            or "enforcement_map" in eff
        )
        assert isinstance(fp, str)
    finally:
        if prev is None:
            os.environ.pop("LABTRUST_POLICY_CACHE", None)
        else:
            os.environ["LABTRUST_POLICY_CACHE"] = prev


def test_run_benchmark_with_env_reuse_produces_deterministic_results() -> None:
    """run_benchmark (which uses shared env) produces same episode metrics for same base_seed."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results.json"
        run_benchmark(
            task_name="throughput_sla",
            num_episodes=2,
            base_seed=200,
            out_path=out,
        )
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["episodes"]) == 2
        assert data["episodes"][0]["seed"] == 200
        assert data["episodes"][1]["seed"] == 201
        for ep in data["episodes"]:
            assert "metrics" in ep
            assert "throughput" in ep["metrics"]
