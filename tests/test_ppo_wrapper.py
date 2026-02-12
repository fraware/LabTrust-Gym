"""
Unit tests for PPO/MARL wrapper: obs dim, reward scale schedule, observation space.
No stable-baselines3 required for get_flat_obs_dim and _reward_scale_for_step.
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.marl.sb3_wrapper import (
    _reward_scale_for_step,
    get_flat_obs_dim,
)


def test_get_flat_obs_dim() -> None:
    single = 1 + 1 + 1 + 1 + 6 + 6 + 8 + 6 + 1 + 1 + 1
    assert get_flat_obs_dim(6, 8) == single
    assert get_flat_obs_dim(6, 8) == 33
    assert get_flat_obs_dim(4, 4) == 1 + 1 + 1 + 1 + 4 + 4 + 4 + 4 + 1 + 1 + 1


def test_reward_scale_for_step_empty_schedule() -> None:
    assert _reward_scale_for_step(0, 80, []) == 1.0
    assert _reward_scale_for_step(40, 80, []) == 1.0


def test_reward_scale_for_step_single_stage() -> None:
    schedule = [(0.0, 0.5)]
    assert _reward_scale_for_step(0, 80, schedule) == 0.5
    assert _reward_scale_for_step(40, 80, schedule) == 0.5
    assert _reward_scale_for_step(80, 80, schedule) == 0.5


def test_reward_scale_for_step_curriculum() -> None:
    schedule = [(0.0, 0.5), (0.5, 1.0)]
    assert _reward_scale_for_step(0, 80, schedule) == 0.5
    assert _reward_scale_for_step(39, 80, schedule) == 0.5
    assert _reward_scale_for_step(40, 80, schedule) == 1.0
    assert _reward_scale_for_step(80, 80, schedule) == 1.0


def test_reward_scale_for_step_zero_max_steps() -> None:
    assert _reward_scale_for_step(0, 0, [(0.0, 0.5)]) == 1.0


def test_make_task_env_obs_space_with_history() -> None:
    """With [env] and gymnasium, make_task_env(obs_history_len=2) has obs dim = single_dim * 2."""
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    from labtrust_gym.baselines.marl.sb3_wrapper import make_task_env

    gym_env, _ = make_task_env(
        task_name="throughput_sla",
        max_steps=80,
        obs_history_len=2,
    )
    single_dim = get_flat_obs_dim(6, 8)
    assert gym_env.observation_space.shape == (single_dim * 2,)
    gym_env.close()


def test_run_ppo_optuna_requires_optuna() -> None:
    """run_ppo_optuna raises ImportError when optuna is not installed."""
    try:
        import optuna  # noqa: F401
        pytest.skip("optuna is installed; cannot test ImportError path")
    except ImportError:
        pass
    from labtrust_gym.baselines.marl.ppo_train import run_ppo_optuna

    with pytest.raises(ImportError, match="optuna"):
        run_ppo_optuna(n_trials=1, timesteps_per_trial=100)
