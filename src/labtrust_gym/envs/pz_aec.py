"""
PettingZoo AEC (Agent-Environment Cycle) wrapper on top of the Parallel env.

Uses PettingZoo's parallel_to_aec conversion; no duplicated logic.
Sequential stepping, agent_selection, observe/step semantics.
Deterministic when used with same seed and action sequence.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from labtrust_gym.envs.pz_parallel import (
    ACTION_NOOP,
    ACTION_TICK,
    LabTrustParallelEnv,
)

try:
    from pettingzoo.utils.conversions import parallel_to_aec
except ImportError:
    parallel_to_aec = None  # type: ignore[misc, assignment]


def labtrust_aec_env(
    num_runners: int = 2,
    dt_s: int = 10,
    reward_config: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Any:
    """
    Build a PettingZoo AEC environment that wraps LabTrustParallelEnv.

    Sequential stepping: agent_selection, observe(), step(action). Same agent set,
    observation/action spaces, and engine as the Parallel env; no logic
    duplication (uses parallel_to_aec).

    Parameters
    ----------
    num_runners : int
        Number of runner agents (default 2).
    dt_s : int
        Simulation time step in seconds (default 10).
    reward_config : dict, optional
        Optional reward hooks (throughput_reward, violation_penalty, blocked_penalty).
    **kwargs
        Passed to LabTrustParallelEnv (e.g. policy_dir).
        reward_config: throughput_reward, violation_penalty, blocked_penalty.

    Returns
    -------
    AECEnv
        PettingZoo AEC (parallel_to_aec + OrderEnforcingWrapper).
    """
    if parallel_to_aec is None:
        raise ImportError(
            "PettingZoo is required for labtrust_aec_env. "
            'Install with: pip install -e ".[env]"'
        )
    parallel_env = LabTrustParallelEnv(
        num_runners=num_runners,
        dt_s=dt_s,
        reward_config=reward_config,
        **kwargs,
    )
    return parallel_to_aec(parallel_env)


__all__ = ["labtrust_aec_env", "ACTION_NOOP", "ACTION_TICK"]
