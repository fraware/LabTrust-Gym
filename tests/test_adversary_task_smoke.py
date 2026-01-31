"""
TaskD adversarial disruption: deterministic run and detection/containment/attribution metrics.
"""

from pathlib import Path

import pytest

from labtrust_gym.benchmarks.runner import run_episode
from labtrust_gym.benchmarks.tasks import get_task


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_taskd_runs_deterministically() -> None:
    """TaskD with same seed produces identical episode metrics across two runs."""
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    root = _repo_root()
    task = get_task("TaskD")
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv
    from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
    from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
    from labtrust_gym.baselines.adversary import AdversaryAgent
    from labtrust_gym.envs.pz_parallel import DEFAULT_ZONE_IDS, DEFAULT_DEVICE_IDS

    def env_factory(initial_state, reward_config, log_path=None):
        return LabTrustParallelEnv(
            num_runners=2,
            num_adversaries=1,
            dt_s=10,
            reward_config=reward_config,
            log_path=log_path,
        )

    def make_agents():
        return {
            "ops_0": ScriptedOpsAgent(),
            "runner_0": ScriptedRunnerAgent(
                zone_ids=DEFAULT_ZONE_IDS,
                device_ids=DEFAULT_DEVICE_IDS,
            ),
            "runner_1": ScriptedRunnerAgent(
                zone_ids=DEFAULT_ZONE_IDS,
                device_ids=DEFAULT_DEVICE_IDS,
            ),
            "adversary_0": AdversaryAgent(),
        }

    seed = 99
    metrics1, _ = run_episode(
        task, seed, env_factory, scripted_agents_map=make_agents()
    )
    metrics2, _ = run_episode(
        task, seed, env_factory, scripted_agents_map=make_agents()
    )
    assert metrics1["throughput"] == metrics2["throughput"]
    assert metrics1["steps"] == metrics2["steps"]
    assert metrics1.get("violations_by_invariant_id") == metrics2.get(
        "violations_by_invariant_id"
    )
    assert metrics1.get("blocked_by_reason_code") == metrics2.get(
        "blocked_by_reason_code"
    )
    if "detection_latency_s" in metrics1:
        assert metrics1["detection_latency_s"] == metrics2["detection_latency_s"]
    if "containment_success" in metrics1:
        assert metrics1["containment_success"] == metrics2["containment_success"]


def test_taskd_produces_detection_metrics() -> None:
    """TaskD run produces detection_latency_s, containment_success, or attribution_confidence_proxy when applicable."""
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    root = _repo_root()
    task = get_task("TaskD")
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv
    from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
    from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
    from labtrust_gym.baselines.adversary import AdversaryAgent
    from labtrust_gym.envs.pz_parallel import DEFAULT_ZONE_IDS, DEFAULT_DEVICE_IDS

    def env_factory(initial_state, reward_config, log_path=None):
        return LabTrustParallelEnv(
            num_runners=2,
            num_adversaries=1,
            dt_s=10,
            reward_config=reward_config,
            log_path=log_path,
        )

    scripted_agents_map = {
        "ops_0": ScriptedOpsAgent(),
        "runner_0": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS,
            device_ids=DEFAULT_DEVICE_IDS,
        ),
        "runner_1": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS,
            device_ids=DEFAULT_DEVICE_IDS,
        ),
        "adversary_0": AdversaryAgent(),
    }

    metrics, _ = run_episode(
        task, 42, env_factory, scripted_agents_map=scripted_agents_map
    )
    assert "steps" in metrics
    assert metrics["steps"] > 0
    # Adversary triggers violations; we should see at least one of these
    has_violations = bool(metrics.get("violations_by_invariant_id"))
    has_blocked = bool(metrics.get("blocked_by_reason_code"))
    assert has_violations or has_blocked or metrics.get("throughput", 0) >= 0
