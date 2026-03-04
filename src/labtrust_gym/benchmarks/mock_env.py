"""
Minimal mock environment implementing BenchmarkEnv for agent-driven security tests.

Used when running scenario_ref or llm_attacker attacks without a full simulation:
provides scripted observations (e.g. specimen_note, scenario_note) so the agent/shield
path can be tested in isolation. Inject adversarial payload into scenario_note or
specimen_note per step. See design_choices.md and security_attack_suite.md.
"""

from __future__ import annotations

from typing import Any


class MockBenchmarkEnv:
    """
    Minimal BenchmarkEnv: fixed agents, scripted obs (specimen_note, scenario_note),
    no real simulation. Step ignores actions and returns trivial rewards/dones.
    """

    def __init__(
        self,
        agents: list[str] | None = None,
        step_obs: dict[str, Any] | None = None,
    ) -> None:
        self._agents = agents or ["ops_0"]
        self._step_obs = step_obs or {}
        self._step_count = 0

    @property
    def agents(self) -> list[str]:
        return list(self._agents)

    def reset(
        self,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self._step_count = 0
        obs = {aid: dict(self._step_obs) for aid in self._agents}
        if not obs:
            obs = {"ops_0": dict(self._step_obs)}
        infos = {}
        return obs, infos

    def step(
        self,
        actions: dict[str, Any],
        action_infos: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[
        dict[str, Any],
        dict[str, float],
        dict[str, bool],
        dict[str, bool],
        dict[str, dict[str, Any]],
    ]:
        self._step_count += 1
        obs = {aid: dict(self._step_obs) for aid in self._agents}
        rewards = {aid: 0.0 for aid in self._agents}
        terminations = {aid: False for aid in self._agents}
        truncations = {aid: False for aid in self._agents}
        infos = {aid: {} for aid in self._agents}
        return obs, rewards, terminations, truncations, infos

    def get_timing_summary(self) -> dict[str, Any]:
        return {"timing_mode": "logical", "episode_time_s": 0, "device_busy_s": {}}

    def get_device_queue_lengths(self) -> dict[str, int]:
        return {}

    def get_device_ids(self) -> list[str]:
        return []

    def get_zone_ids(self) -> list[str]:
        return []

    def get_dt_s(self) -> int:
        return 1

    def close(self) -> None:
        pass

    def set_step_obs(self, step_obs: dict[str, Any]) -> None:
        """Update the observation returned at each step (e.g. inject scenario_note)."""
        self._step_obs = dict(step_obs)
