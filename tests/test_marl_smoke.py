"""
MARL smoke test: PPO train/eval pipeline (guarded by LABTRUST_MARL_SMOKE=1).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


def test_marl_smoke_ppo_train_tiny() -> None:
    """With LABTRUST_MARL_SMOKE=1, train PPO for tiny steps and ensure no crash."""
    if os.environ.get("LABTRUST_MARL_SMOKE") != "1":
        pytest.skip("Set LABTRUST_MARL_SMOKE=1 to run MARL smoke tests")
    pytest.importorskip("stable_baselines3")
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")

    from labtrust_gym.baselines.marl.ppo_train import train_ppo

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ppo"
        result = train_ppo(
            task_name="TaskA",
            timesteps=500,
            seed=42,
            out_dir=out,
            log_interval=250,
            verbose=0,
        )
        assert Path(result["model_path"]).exists()
        assert "eval_metrics" in result
        assert "mean_reward" in result["eval_metrics"]


def test_marl_smoke_ppo_eval() -> None:
    """With LABTRUST_MARL_SMOKE=1, run eval after a tiny train."""
    if os.environ.get("LABTRUST_MARL_SMOKE") != "1":
        pytest.skip("Set LABTRUST_MARL_SMOKE=1 to run MARL smoke tests")
    pytest.importorskip("stable_baselines3")
    pytest.importorskip("gymnasium")

    from labtrust_gym.baselines.marl.ppo_train import train_ppo
    from labtrust_gym.baselines.marl.ppo_eval import eval_ppo

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ppo"
        train_ppo(
            task_name="TaskA",
            timesteps=300,
            seed=7,
            out_dir=out,
            verbose=0,
        )
        model_path = out / "model.zip"
        metrics = eval_ppo(
            model_path=str(model_path),
            task_name="TaskA",
            episodes=2,
            seed=100,
            out_path=out / "eval_out.json",
        )
        assert "mean_reward" in metrics
        assert "episode_rewards" in metrics
        assert len(metrics["episode_rewards"]) == 2
        assert (out / "eval_out.json").exists()
