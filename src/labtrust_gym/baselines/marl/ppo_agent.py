"""
PPO agent for eval-agent: load a trained model.zip and act as ops_0 in run_benchmark.

Use with: labtrust eval-agent --task throughput_sla --agent labtrust_gym.baselines.marl.ppo_agent:PPOAgent ...
Set LABTRUST_PPO_MODEL to the path to model.zip (default: labtrust_runs/ppo_out/model.zip).
Loads train_config.json next to model for device_ids and obs_history_len when present.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from labtrust_gym.baselines.marl.sb3_wrapper import _flatten_obs, _one_hot_agent


def _get_model_path(repo_root: Path | None = None) -> Path:
    path = os.environ.get("LABTRUST_PPO_MODEL", "labtrust_runs/ppo_out/model.zip")
    p = Path(path)
    if not p.is_absolute():
        if repo_root is not None:
            p = Path(repo_root) / p
        else:
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

    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = Path(repo_root) if repo_root is not None else None
        self._model = None
        self._device_ids: list[str] = []
        self._n_d = 6
        self._n_status = 8
        self._obs_history_len = 1
        self._obs_history: list[Any] = []
        self._include_agent_id = False
        self._num_agents = 1

    def _load_model(self) -> None:
        if self._model is not None:
            return
        try:
            from stable_baselines3 import PPO
        except ImportError:
            raise ImportError('PPOAgent requires stable-baselines3. Install with: pip install -e ".[marl]"') from None
        path = _get_model_path(self._repo_root)
        if not path.is_file():
            raise FileNotFoundError(
                f"PPO model not found at {path}. "
                "Train with: labtrust train-ppo --out <dir>; set LABTRUST_PPO_MODEL to <dir>/model.zip"
            )
        self._model = PPO.load(str(path))
        cfg_path = path.parent / "train_config.json"
        if cfg_path.exists():
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    tc = json.load(f)
                if isinstance(tc.get("device_ids"), list):
                    self._device_ids = [str(x) for x in tc["device_ids"]]
                self._obs_history_len = max(1, int(tc.get("obs_history_len", 1)))
                if isinstance(tc.get("n_d"), int):
                    self._n_d = tc["n_d"]
                if isinstance(tc.get("n_status"), int):
                    self._n_status = tc["n_status"]
                self._include_agent_id = bool(tc.get("include_agent_id", False))
                self._num_agents = max(1, int(tc.get("num_agents", 1)))
            except Exception:
                pass
        if not self._device_ids:
            try:
                from labtrust_gym.envs.pz_parallel import DEFAULT_DEVICE_IDS

                self._device_ids = list(DEFAULT_DEVICE_IDS)
            except Exception:
                self._device_ids = ["DEV_CHEM_A_01"]

    def reset(
        self,
        seed: int,
        policy_summary: dict[str, Any] | None = None,
        partner_id: str | None = None,
        timing_mode: str = "explicit",
    ) -> None:
        """Called at episode start. Clears observation history for new episode."""
        self._load_model()
        self._obs_history = []

    def _decode_queue_run_action_info(self, observation: dict[str, Any]) -> dict[str, Any]:
        """Decode device_id and work_id from observation for QUEUE_RUN (action 2)."""
        qbd = observation.get("queue_by_device") or []
        device_ids = getattr(self, "_device_ids", None) or ["DEV_CHEM_A_01"]
        work_id = "ppo_work"
        device_id = device_ids[0] if device_ids else "DEV_CHEM_A_01"
        for idx, entry in enumerate(qbd):
            if not isinstance(entry, dict):
                continue
            if (entry.get("queue_len") or 0) > 0:
                head = entry.get("queue_head") or "W"
                if isinstance(head, str) and head.strip():
                    work_id = head.strip()
                if idx < len(device_ids):
                    device_id = device_ids[idx]
                break
        return {
            "work_id": work_id,
            "device_id": device_id,
            "priority": "ROUTINE",
        }

    def act(self, observation: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Return (action_index, action_info) for ops_0. Uses same obs flattening as training."""
        self._load_model()
        flat = _flatten_obs(
            observation,
            n_d=self._n_d,
            n_status=self._n_status,
        )
        flat = np.asarray(flat, dtype=np.float32).flatten()
        if self._obs_history_len > 1:
            if len(self._obs_history) == 0:
                self._obs_history = [flat] * self._obs_history_len
            else:
                self._obs_history = (self._obs_history + [flat])[-self._obs_history_len :]
            obs_input = np.concatenate(self._obs_history, axis=0)
        else:
            obs_input = flat
        if self._include_agent_id and self._num_agents >= 1:
            obs_input = np.concatenate(
                [np.asarray(obs_input, dtype=np.float32).flatten(), _one_hot_agent(0, self._num_agents)],
                axis=0,
            )
        action, _ = self._model.predict(obs_input, deterministic=True)
        action = int(action)
        action_info: dict[str, Any] = {}
        if action == 2:
            action_info = self._decode_queue_run_action_info(observation)
        return action, action_info


class MarlPPOPerAgentAgent:
    """
    Per-agent agent for scale path (N > N_max): one shared PPO model, act(obs, agent_id)
    uses one_hot(agent_index) so the same policy can act for any agent.
    Used when coord method is marl_ppo and scripted_agents_map is populated by the runner.
    """

    def __init__(
        self,
        model_path: str | Path,
        agent_order: list[str] | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self._model_path = Path(model_path)
        self._agent_order = list(agent_order) if agent_order else []
        self._repo_root = Path(repo_root) if repo_root else None
        self._model: Any = None
        self._n_d = 6
        self._n_status = 8
        self._obs_history_len = 1
        self._agent_obs_histories: dict[str, list[Any]] = {}
        self._include_agent_id = True
        self._num_agents = 5
        self._device_ids: list[str] = []

    def _load_model(self) -> None:
        if self._model is not None:
            return
        try:
            from stable_baselines3 import PPO
        except ImportError:
            raise ImportError(
                'MarlPPOPerAgentAgent requires stable-baselines3. Install with: pip install -e ".[marl]"'
            ) from None
        if not self._model_path.is_file():
            raise FileNotFoundError(f"PPO model not found at {self._model_path}")
        self._model = PPO.load(str(self._model_path))
        cfg_path = self._model_path.parent / "train_config.json"
        if cfg_path.exists():
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    tc = json.load(f)
                self._n_d = int(tc.get("n_d", 6))
                self._n_status = int(tc.get("n_status", 8))
                self._obs_history_len = max(1, int(tc.get("obs_history_len", 1)))
                self._include_agent_id = bool(tc.get("include_agent_id", True))
                self._num_agents = max(1, int(tc.get("num_agents", 5)))
                if isinstance(tc.get("device_ids"), list):
                    self._device_ids = [str(x) for x in tc["device_ids"]]
            except Exception:
                pass
        if not self._device_ids:
            try:
                from labtrust_gym.envs.pz_parallel import DEFAULT_DEVICE_IDS

                self._device_ids = list(DEFAULT_DEVICE_IDS)
            except Exception:
                self._device_ids = ["DEV_CHEM_A_01"]

    def _agent_index(self, agent_id: str) -> int:
        if self._agent_order:
            try:
                return self._agent_order.index(agent_id)
            except ValueError:
                pass
        return 0

    def _decode_queue_run_action_info(self, observation: dict[str, Any]) -> dict[str, Any]:
        qbd = observation.get("queue_by_device") or []
        device_ids = self._device_ids or ["DEV_CHEM_A_01"]
        work_id = "ppo_work"
        device_id = device_ids[0] if device_ids else "DEV_CHEM_A_01"
        for idx, entry in enumerate(qbd):
            if not isinstance(entry, dict):
                continue
            if (entry.get("queue_len") or 0) > 0:
                head = entry.get("queue_head") or "W"
                if isinstance(head, str) and head.strip():
                    work_id = head.strip()
                if idx < len(device_ids):
                    device_id = device_ids[idx]
                break
        return {
            "work_id": work_id,
            "device_id": device_id,
            "priority": "ROUTINE",
        }

    def act(self, observation: dict[str, Any], agent_id: str) -> tuple[int, dict[str, Any]]:
        """Return (action_index, action_info) for agent_id using shared policy + one_hot."""
        self._load_model()
        flat = _flatten_obs(observation, n_d=self._n_d, n_status=self._n_status)
        flat = np.asarray(flat, dtype=np.float32).flatten()
        if agent_id not in self._agent_obs_histories:
            self._agent_obs_histories[agent_id] = [flat] * self._obs_history_len
        else:
            hist = self._agent_obs_histories[agent_id] + [flat]
            self._agent_obs_histories[agent_id] = hist[-self._obs_history_len :]
        stacked = np.concatenate(self._agent_obs_histories[agent_id], axis=0)
        if self._include_agent_id and self._num_agents >= 1:
            idx = min(self._agent_index(agent_id), self._num_agents - 1)
            stacked = np.concatenate(
                [stacked, _one_hot_agent(idx, self._num_agents)],
                axis=0,
            )
        action, _ = self._model.predict(stacked.astype(np.float32), deterministic=True)
        action = int(action)
        action_info: dict[str, Any] = {}
        if action == 2:
            action_info = self._decode_queue_run_action_info(observation)
        return action, action_info
