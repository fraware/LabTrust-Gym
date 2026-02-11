"""
PPO agent for eval-agent: load a trained model.zip and act as ops_0 in run_benchmark.

Use with: labtrust eval-agent --task throughput_sla --agent labtrust_gym.baselines.marl.ppo_agent:PPOAgent ...
Set LABTRUST_PPO_MODEL to the path to model.zip (default: labtrust_runs/ppo_out/model.zip).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.marl.sb3_wrapper import _flatten_obs


def _get_model_path() -> Path:
    path = os.environ.get("LABTRUST_PPO_MODEL", "labtrust_runs/ppo_out/model.zip")
    p = Path(path)
    if not p.is_absolute():
        try:
            from labtrust_gym.config import get_repo_root
            p = get_repo_root() / p
        except Exception:
            p = Path.cwd() / p
    return p


class PPOAgent:
    """
    LabTrustAgent that uses a trained stable-baselines3 PPO model for ops_0.
    Model path: LABTRUST_PPO_MODEL env or labtrust_runs/ppo_out/model.zip.
    """

    def __init__(self) -> None:
        self._model = None
        self._device_ids: list[str] = []
        self._n_d = 6
        self._n_status = 8

    def _load_model(self) -> None:
        if self._model is not None:
            return
        try:
            from stable_baselines3 import PPO
        except ImportError:
            raise ImportError(
                "PPOAgent requires stable-baselines3. Install with: pip install -e \".[marl]\""
            ) from None
        path = _get_model_path()
        if not path.is_file():
            raise FileNotFoundError(
                f"PPO model not found at {path}. "
                "Train with: labtrust train-ppo --out <dir>; set LABTRUST_PPO_MODEL to <dir>/model.zip"
            )
        self._model = PPO.load(str(path))
        self._device_ids = ["DEV_CHEM_A_01"]

    def reset(
        self,
        seed: int,
        policy_summary: dict[str, Any] | None = None,
        partner_id: str | None = None,
        timing_mode: str = "explicit",
    ) -> None:
        """Called at episode start. Optional."""
        self._load_model()

    def act(self, observation: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Return (action_index, action_info) for ops_0. Uses same obs flattening as training."""
        self._load_model()
        flat = _flatten_obs(
            observation,
            n_d=self._n_d,
            n_status=self._n_status,
        )
        action, _ = self._model.predict(flat, deterministic=True)
        action = int(action)
        action_info: dict[str, Any] = {}
        if action == 2:
            action_info = {
                "work_id": "ppo_work",
                "device_id": self._device_ids[0] if self._device_ids else "DEV_CHEM_A_01",
                "priority": "ROUTINE",
            }
        return action, action_info
