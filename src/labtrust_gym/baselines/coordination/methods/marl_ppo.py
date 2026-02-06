"""
MARL PPO coordination: uses Stable-Baselines3 PPO policy when [marl] extra present.
Otherwise stub that raises a clear error (skipped in studies unless [marl] installed).
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.baselines.coordination.interface import CoordinationMethod

MARL_IMPORT_ERROR = "marl_ppo requires stable-baselines3 and gymnasium. Install with: pip install labtrust-gym[marl]"


def _check_sb3() -> None:
    try:
        import gymnasium  # noqa: F401
        import stable_baselines3  # noqa: F401
    except ImportError as e:
        raise ImportError(MARL_IMPORT_ERROR) from e


class MarlPPOStub(CoordinationMethod):
    """
    Stub when SB3 not installed. propose_actions raises; use only when [marl] present.
    When SB3 is available, a real implementation would wrap the trained policy and
    map obs -> action per agent (e.g. single policy with agent index in obs).
    """

    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = model_path
        self._policy: Any = None
        self._env: Any = None

    @property
    def method_id(self) -> str:
        return "marl_ppo"

    def reset(self, seed: int, policy: dict[str, Any], scale_config: dict[str, Any]) -> None:
        _check_sb3()
        if self._model_path:
            try:
                from stable_baselines3 import PPO

                self._policy = PPO.load(self._model_path)
            except Exception:
                self._policy = None
        else:
            self._policy = None

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        _check_sb3()
        if self._policy is None:
            raise NotImplementedError(
                "marl_ppo requires a trained model. Use --coord-method marl_ppo with "
                "a model path (e.g. from labtrust train-ppo --out runs/ppo) or install "
                "and use a different coordination method for this run."
            )
        agents = sorted(obs.keys())
        out: dict[str, dict[str, Any]] = {}
        for agent_id in agents:
            o = obs.get(agent_id) or {}
            try:
                action, _ = self._policy.predict(o, deterministic=True)
                idx = int(action) if hasattr(action, "item") else int(action)
                idx = max(0, min(5, idx))
                out[agent_id] = {"action_index": idx}
            except Exception:
                out[agent_id] = {"action_index": 0}
        return out


def make_marl_ppo_if_available(model_path: str | None = None, **kwargs: Any) -> CoordinationMethod | None:
    """Return MarlPPOStub (or future PPO wrapper) if SB3 available, else None."""
    try:
        _check_sb3()
        return MarlPPOStub(model_path=model_path)
    except ImportError:
        return None
