"""
Environment wrappers for Gym/PettingZoo-style APIs.

Provides LabTrustParallelEnv (PettingZoo Parallel API) and labtrust_aec_env
(agent-environment cycle). Both wrap the core engine; require optional
dependency: pip install -e \".[env]\".
"""

from __future__ import annotations

try:
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv
except ImportError:
    LabTrustParallelEnv = None  # type: ignore[assignment,misc]

try:
    from labtrust_gym.envs.pz_aec import labtrust_aec_env
except ImportError:
    labtrust_aec_env = None  # type: ignore[assignment]

__all__ = ["LabTrustParallelEnv", "labtrust_aec_env"]
