"""Minimal BenchmarkTask for the extension example."""

from __future__ import annotations

from labtrust_gym.benchmarks.tasks import BenchmarkTask


class ExampleTask(BenchmarkTask):
    """Minimal task: uses default initial_state from BenchmarkTask."""

    def __init__(self) -> None:
        super().__init__(
            name="example_task",
            max_steps=20,
            scripted_agents=["ops_0", "runner_0", "runner_1"],
            reward_config={"throughput_reward": 1.0},
        )
