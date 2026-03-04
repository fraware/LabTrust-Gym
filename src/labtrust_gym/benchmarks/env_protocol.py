"""
Protocol for the environment used by the benchmark runner (run_episode).

This is the only supported env interface for run_episode. Implementations
(e.g. LabTrustParallelEnv) provide reset, step, agents, timing and device/zone
access without exposing private attributes. The runner depends on this
interface only, not on a concrete env type.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BenchmarkEnv(Protocol):
    """Environment contract for run_episode: reset, step, agents, timing, device/zone IDs."""

    @property
    def agents(self) -> list[str]:
        """Current list of agent IDs."""
        ...

    def reset(
        self,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Reset the environment; return (observations, infos)."""
        ...

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
        """Step all agents; return (observations, rewards, terminations, truncations, infos)."""
        ...

    def get_timing_summary(self) -> dict[str, Any]:
        """Return timing_mode, episode_time_s, device_busy_s for metrics."""
        ...

    def get_device_queue_lengths(self) -> dict[str, int]:
        """Return current queue length per device (timing_mode simulated)."""
        ...

    def get_device_ids(self) -> list[str]:
        """Return device IDs in stable order (for harness and metrics)."""
        ...

    def get_zone_ids(self) -> list[str]:
        """Return zone IDs in stable order (for harness and metrics)."""
        ...

    def get_dt_s(self) -> int:
        """Return simulation time step in seconds."""
        ...

    def close(self) -> None:
        """Release resources."""
        ...


__all__ = ["BenchmarkEnv"]
