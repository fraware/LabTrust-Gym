"""
Evaluate a trained PPO policy for N episodes with deterministic seeds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from labtrust_gym.baselines.marl.ppo_train import _eval_policy


def eval_ppo(
    model_path: str,
    task_name: str = "TaskA",
    episodes: int = 50,
    seed: int = 123,
    out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Load model, run N episodes with deterministic seeds, return and optionally save metrics.
    """
    metrics = _eval_policy(
        model_path=model_path,
        task_name=task_name,
        n_episodes=episodes,
        seed=seed,
    )
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)
    return metrics
