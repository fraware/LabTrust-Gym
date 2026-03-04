"""
MARL PPO coordination: shared policy with agent_id in observation.

Uses a single PPO model trained with include_agent_id=True (obs = flat_obs + one_hot(agent_id)).
Proposes actions for all agents by feeding each agent's observation plus one-hot agent index
to the same policy. Requires stable-baselines3 and gymnasium ([marl] extra).
When no model path is provided or model load fails, raises a clear error (coordination runs exclude
marl_ppo from full pack unless a checkpoint is supplied).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.coordination.interface import CoordinationMethod
from labtrust_gym.baselines.marl.sb3_wrapper import _flatten_obs, _one_hot_agent

MARL_IMPORT_ERROR = "marl_ppo requires stable-baselines3 and gymnasium. Install with: pip install labtrust-gym[marl]"


def _check_sb3() -> None:
    try:
        import gymnasium  # noqa: F401
        import stable_baselines3  # noqa: F401
    except ImportError as e:
        raise ImportError(MARL_IMPORT_ERROR) from e


class MarlPPOCoordination(CoordinationMethod):
    """
    Coordination method using a shared PPO policy with agent_id in observation.
    Loads model and train_config from model_path; each agent's obs is flattened,
    optionally stacked with history, and concatenated with one_hot(agent_index).
    """

    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = model_path
        self._policy: Any = None
        self._n_d = 6
        self._n_status = 8
        self._obs_history_len = 1
        self._include_agent_id = True
        self._num_agents = 5
        self._agent_obs_histories: dict[str, list[Any]] = {}

    @property
    def method_id(self) -> str:
        return "marl_ppo"

    def reset(self, seed: int, policy: dict[str, Any], scale_config: dict[str, Any]) -> None:
        _check_sb3()
        self._agent_obs_histories.clear()
        if not self._model_path:
            self._policy = None
            return
        try:
            from stable_baselines3 import PPO

            self._policy = PPO.load(str(self._model_path))
            cfg_path = Path(self._model_path).parent / "train_config.json"
            if cfg_path.exists():
                with open(cfg_path, encoding="utf-8") as f:
                    tc = json.load(f)
                self._n_d = int(tc.get("n_d", 6))
                self._n_status = int(tc.get("n_status", 8))
                self._obs_history_len = max(1, int(tc.get("obs_history_len", 1)))
                self._include_agent_id = bool(tc.get("include_agent_id", True))
                self._num_agents = max(1, int(tc.get("num_agents", 5)))
        except Exception:
            self._policy = None

    def _obs_to_vector(self, agent_id: str, obs_dict: dict[str, Any], agent_index: int) -> Any:
        """Flatten obs, update per-agent history, return vector for policy (stacked + one_hot if enabled)."""
        import numpy as np

        flat = _flatten_obs(obs_dict, n_d=self._n_d, n_status=self._n_status)
        flat = np.asarray(flat, dtype=np.float32).flatten()
        if agent_id not in self._agent_obs_histories:
            self._agent_obs_histories[agent_id] = [flat] * self._obs_history_len
        else:
            self._agent_obs_histories[agent_id] = (self._agent_obs_histories[agent_id] + [flat])[
                -self._obs_history_len :
            ]
        stacked = np.concatenate(self._agent_obs_histories[agent_id], axis=0)
        if self._include_agent_id and self._num_agents >= 1:
            idx = min(agent_index, self._num_agents - 1)
            stacked = np.concatenate(
                [stacked, _one_hot_agent(idx, self._num_agents)],
                axis=0,
            )
        return stacked.astype(np.float32)

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        _check_sb3()
        if self._policy is None:
            raise RuntimeError(
                "marl_ppo requires a trained model. Use --coord-method marl_ppo with "
                "model_path (e.g. from labtrust train-ppo --out runs/ppo) or use a different "
                "coordination method for this run."
            )
        agents = sorted(obs.keys())
        out: dict[str, dict[str, Any]] = {}
        for i, agent_id in enumerate(agents):
            o = obs.get(agent_id) or {}
            try:
                vec = self._obs_to_vector(agent_id, o, i)
                action, _ = self._policy.predict(vec, deterministic=True)
                idx = int(action) if hasattr(action, "item") else int(action)
                idx = max(0, min(5, idx))
                out[agent_id] = {"action_index": idx}
            except Exception:
                out[agent_id] = {"action_index": 0}
        return out

    def get_learning_metadata(self) -> dict[str, Any] | None:
        """Return study-track learning metadata when a model is loaded (inference-only)."""
        if self._policy is None or not self._model_path:
            return None
        path = Path(self._model_path)
        if not path.is_file():
            return {"enabled": True}
        try:
            with open(path, "rb") as f:
                checkpoint_sha = hashlib.sha256(f.read()).hexdigest()
        except Exception:
            return {"enabled": True}
        return {"enabled": True, "checkpoint_sha": checkpoint_sha}


def make_marl_ppo_if_available(model_path: str | None = None, **kwargs: Any) -> CoordinationMethod | None:
    """Return MarlPPOCoordination if SB3 available, else None."""
    try:
        _check_sb3()
        return MarlPPOCoordination(model_path=model_path)
    except ImportError:
        return None
