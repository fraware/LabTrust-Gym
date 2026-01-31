"""MARL baselines: PPO (stable-baselines3) training and evaluation."""

from __future__ import annotations

try:
    from labtrust_gym.baselines.marl.sb3_wrapper import (
        LabTrustGymnasiumWrapper,
        make_task_env,
    )
except ImportError:
    LabTrustGymnasiumWrapper = None  # type: ignore[misc, assignment]
    make_task_env = None  # type: ignore[assignment]

__all__ = ["LabTrustGymnasiumWrapper", "make_task_env"]
