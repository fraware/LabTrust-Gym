"""
Evaluate a trained PPO policy for N episodes with deterministic seeds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.marl.ppo_train import _eval_policy


def eval_ppo(
    model_path: str,
    task_name: str = "throughput_sla",
    episodes: int = 50,
    seed: int = 123,
    out_path: Path | None = None,
    train_config_path: str | None = None,
) -> dict[str, Any]:
    """
    Load model, run N episodes with deterministic seeds, return and optionally save metrics.
    If train_config_path is not set, looks for train_config.json next to model.zip so
    eval uses the same obs_history_len (and other settings) as training.
    """
    path = Path(model_path)
    default_cfg = str(path.parent / "train_config.json") if path.parent else None
    cfg_path = train_config_path or default_cfg
    if cfg_path and not Path(cfg_path).exists():
        cfg_path = None
    metrics = _eval_policy(
        model_path=model_path,
        task_name=task_name,
        n_episodes=episodes,
        seed=seed,
        train_config_path=cfg_path,
    )
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)
    return metrics
