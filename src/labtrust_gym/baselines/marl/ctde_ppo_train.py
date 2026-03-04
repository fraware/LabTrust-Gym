"""
CTDE (Centralized Training, Decentralized Execution) training entry point.

Trains a shared policy with agent_id in observation; saves policy and train_config
with algorithm "ctde" so eval and marl_ppo can load it. The env wrapper exposes
global_state and global_state_prev in step info for future central critic use.

Current implementation: policy is trained with standard PPO (same as train_ppo).
Central critic (value from global state) and advantage from central value are
future work; the pipeline and config shape are in place.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.marl.ppo_train import train_ppo


def train_ctde_ppo(
    task_name: str = "throughput_sla",
    timesteps: int = 50_000,
    seed: int = 123,
    out_dir: Path | None = None,
    log_interval: int = 1000,
    verbose: int = 1,
    net_arch: list[int] | None = None,
    train_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Train policy for CTDE: same as train_ppo but writes algorithm "ctde" in train_config.
    Saves model and train_config; eval and marl_ppo load the policy unchanged.
    """
    result = train_ppo(
        task_name=task_name,
        timesteps=timesteps,
        seed=seed,
        out_dir=out_dir,
        log_interval=log_interval,
        verbose=verbose,
        net_arch=net_arch,
        train_config=train_config,
    )
    out_path = Path(result["model_path"]).parent
    cfg_path = out_path / "train_config.json"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["algorithm"] = "ctde"
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    result["algorithm"] = "ctde"
    return result
