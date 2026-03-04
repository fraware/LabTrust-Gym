"""
Environment wrappers for Gym/PettingZoo-style APIs.

Provides LabTrustParallelEnv (PettingZoo Parallel API) and labtrust_aec_env
(agent-environment cycle). Both wrap the core engine; require optional
dependency: pip install -e \".[env]\".
"""

from __future__ import annotations

from labtrust_gym.envs.action_contract import (
    ACTION_MOVE,
    ACTION_NOOP,
    ACTION_OPEN_DOOR,
    ACTION_QUEUE_RUN,
    ACTION_START_RUN,
    ACTION_TICK,
    NUM_ACTION_TYPES,
    VALID_ACTION_INDICES,
)

try:
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv
except ImportError:
    LabTrustParallelEnv = None  # type: ignore[assignment,misc]

try:
    from labtrust_gym.envs.pz_aec import labtrust_aec_env
except ImportError:
    labtrust_aec_env = None  # type: ignore[assignment]

try:
    from labtrust_gym.envs.vectorized import AsyncLabTrustVectorEnv, LabTrustVectorEnv
except ImportError:
    LabTrustVectorEnv = None  # type: ignore[assignment,misc]
    AsyncLabTrustVectorEnv = None  # type: ignore[assignment,misc]

__all__ = [
    "AsyncLabTrustVectorEnv",
    "ACTION_MOVE",
    "ACTION_NOOP",
    "ACTION_OPEN_DOOR",
    "ACTION_QUEUE_RUN",
    "ACTION_START_RUN",
    "ACTION_TICK",
    "LabTrustParallelEnv",
    "LabTrustVectorEnv",
    "NUM_ACTION_TYPES",
    "VALID_ACTION_INDICES",
    "labtrust_aec_env",
]
