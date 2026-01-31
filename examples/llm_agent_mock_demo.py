"""
Demo: TaskB with LLMAgent(mock) + scripted runners.

Uses MockDeterministicBackend (offline-safe, deterministic). No API calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
_src = _root / "src"
if __name__ == "__main__" and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

try:
    from labtrust_gym.baselines.llm.agent import LLMAgent, MockDeterministicBackend
    from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
    from labtrust_gym.benchmarks.runner import run_episode
    from labtrust_gym.benchmarks.tasks import get_task
    from labtrust_gym.envs.pz_parallel import (
        DEFAULT_DEVICE_IDS,
        DEFAULT_ZONE_IDS,
        LabTrustParallelEnv,
    )
except ImportError as e:
    print("Requires labtrust-gym and env deps. Install: pip install -e '.[env]'")
    raise SystemExit(1) from e


def main() -> None:
    task = get_task("TaskB")

    def env_factory(initial_state, reward_config, log_path=None):
        return LabTrustParallelEnv(
            num_runners=2,
            num_adversaries=0,
            dt_s=10,
            reward_config=reward_config or {},
            log_path=log_path,
        )

    mock_backend = MockDeterministicBackend(default_action_type=0)
    llm_agent = LLMAgent(backend=mock_backend)
    scripted_agents_map = {
        "ops_0": llm_agent,
        "runner_0": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS,
            device_ids=DEFAULT_DEVICE_IDS,
        ),
        "runner_1": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS,
            device_ids=DEFAULT_DEVICE_IDS,
        ),
    }

    metrics, _ = run_episode(
        task,
        42,
        env_factory,
        scripted_agents_map=scripted_agents_map,
    )
    print("TaskB with LLMAgent(mock) + scripted runners:")
    print("  throughput:", metrics.get("throughput", 0))
    print("  steps:", metrics.get("steps", 0))
    print("  violations:", metrics.get("violations_by_invariant_id", {}))


if __name__ == "__main__":
    main()
