"""
Helpers for PettingZoo / Gymnasium API conformance.

LabTrustParallelEnv observations intentionally include LLM/context keys beyond the
declared Dict RL space (zone_id, work_list, role_id, ...). Official PettingZoo
``api_test`` requires ``observation_space.contains(obs)``, so AEC conformance
runs against a projection that keeps only declared space keys. Parallel
``parallel_api_test`` does not enforce Dict.contains and runs on the raw env.
"""

from __future__ import annotations

from typing import Any

try:
    from pettingzoo.utils.env import ParallelEnv as _ParallelEnv
except ImportError:
    _ParallelEnv = None  # type: ignore[misc, assignment]


def project_obs_to_space(obs: dict[str, Any], space: Any) -> dict[str, Any]:
    """Return observation restricted to keys declared in a Dict space."""
    if space is None or not hasattr(space, "spaces"):
        return dict(obs)
    return {k: obs[k] for k in space.spaces.keys() if k in obs}


if _ParallelEnv is not None:

    class ProjectObsToSpaceParallel(_ParallelEnv):  # type: ignore[misc, valid-type]
        """
        ParallelEnv wrapper that projects each agent observation onto
        ``observation_space(agent)`` keys so Dict.contains succeeds.
        """

        metadata = {"name": "labtrust_project_obs_v0", "render_modes": []}

        def __init__(self, env: Any) -> None:
            super().__init__()
            self._env = env
            self.metadata = getattr(env, "metadata", self.metadata)
            self.possible_agents = list(env.possible_agents)
            self.agents = list(getattr(env, "agents", self.possible_agents))
            self.observation_spaces = {
                a: env.observation_space(a) for a in self.possible_agents
            }
            self.action_spaces = {a: env.action_space(a) for a in self.possible_agents}

        def observation_space(self, agent: str) -> Any:
            return self.observation_spaces[agent]

        def action_space(self, agent: str) -> Any:
            return self.action_spaces[agent]

        def _project_batch(self, obs: dict[str, Any]) -> dict[str, Any]:
            return {
                agent: project_obs_to_space(o, self.observation_space(agent))
                for agent, o in obs.items()
            }

        def reset(
            self,
            seed: int | None = None,
            options: dict[str, Any] | None = None,
        ) -> tuple[dict[str, Any], dict[str, Any]]:
            obs, infos = self._env.reset(seed=seed, options=options)
            self.agents = list(self._env.agents)
            return self._project_batch(obs), infos

        def step(
            self,
            actions: dict[str, Any],
        ) -> tuple[
            dict[str, Any],
            dict[str, float],
            dict[str, bool],
            dict[str, bool],
            dict[str, dict[str, Any]],
        ]:
            obs, rewards, terminations, truncations, infos = self._env.step(actions)
            self.agents = list(self._env.agents)
            return (
                self._project_batch(obs),
                rewards,
                terminations,
                truncations,
                infos,
            )

        def close(self) -> None:
            self._env.close()

        @property
        def unwrapped(self) -> Any:
            return getattr(self._env, "unwrapped", self._env)

else:
    ProjectObsToSpaceParallel = None  # type: ignore[misc, assignment]


__all__ = [
    "ProjectObsToSpaceParallel",
    "project_obs_to_space",
]
