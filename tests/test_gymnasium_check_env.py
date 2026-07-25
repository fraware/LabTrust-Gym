"""
Gymnasium check_env for LabTrustGymnasiumWrapper.

Requires: pip install -e ".[env]" (gymnasium + pettingzoo). Skips if missing.
"""

from __future__ import annotations

import pytest

pytest.importorskip("gymnasium")
pytest.importorskip("pettingzoo")

from gymnasium.utils.env_checker import check_env

from labtrust_gym.baselines.marl.sb3_wrapper import LabTrustGymnasiumWrapper
from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv


def test_labtrust_gymnasium_wrapper_check_env() -> None:
    """Official Gymnasium check_env against LabTrustGymnasiumWrapper."""
    if LabTrustGymnasiumWrapper is None:
        pytest.skip("LabTrustGymnasiumWrapper requires gymnasium")
    raw = LabTrustParallelEnv(num_runners=1)
    env = LabTrustGymnasiumWrapper(raw, max_steps=20, num_action_types=6)
    try:
        check_env(env, skip_render_check=True)
    finally:
        env.close()
        raw.close()
