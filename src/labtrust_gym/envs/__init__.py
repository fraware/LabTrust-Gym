"""LabTrust-Gym environment wrappers (PettingZoo Parallel, AEC, etc.)."""

from __future__ import annotations

try:
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv
except ImportError:
    LabTrustParallelEnv = None  # type: ignore[misc, assignment]

try:
    from labtrust_gym.envs.pz_aec import labtrust_aec_env
except ImportError:
    labtrust_aec_env = None  # type: ignore[misc, assignment]

__all__ = ["LabTrustParallelEnv", "labtrust_aec_env"]
