"""
Vectorized env wrapper: N LabTrustParallelEnv instances in one process.

Synchronous step over the vector; each env gets its own seed (base_seed + env_index).
Respects reset(options=...) with timing_mode, dt_s; same agent list and
observation/action contract per env. See design_choices.md 10.1 and pettingzoo_api.md.

LabTrustVectorEnv also offers reset_async() and step_async() for async/await loops
(via asyncio.to_thread). AsyncLabTrustVectorEnv runs reset/step in parallel via a
thread pool (same sync API; no separate async/await). Use for overlapping env stepping
when steps release the GIL (e.g. numpy); for maximum parallelism across many envs,
tune max_workers or use a process-pool variant (not provided).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv


class LabTrustVectorEnv:
    """
    Holds N LabTrustParallelEnv instances; reset() and step() operate on all envs.
    Batch size N from constructor; each env gets seed base_seed + env_index.
    """

    def __init__(
        self,
        num_envs: int,
        *,
        base_seed: int = 0,
        env_factory: Any = None,
        **kwargs: Any,
    ) -> None:
        """
        Create num_envs envs. If env_factory is given, call env_factory() for each;
        else instantiate LabTrustParallelEnv(**kwargs) for each.
        """
        self._num_envs = num_envs
        self._base_seed = base_seed
        if env_factory is not None and callable(env_factory):
            self._envs = [env_factory() for _ in range(num_envs)]
        else:
            self._envs = [LabTrustParallelEnv(**kwargs) for _ in range(num_envs)]

    @property
    def num_envs(self) -> int:
        return self._num_envs

    def reset(
        self,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Reset all envs. Each env gets seed = (seed or base_seed) + env_index.
        Returns (observations_list, infos_list) where observations_list[i] is
        the obs dict for env i (agent -> obs), infos_list[i] is infos for env i.
        """
        base = seed if seed is not None else self._base_seed
        observations_list: list[dict[str, Any]] = []
        infos_list: list[dict[str, Any]] = []
        for i, env in enumerate(self._envs):
            obs, infos = env.reset(seed=base + i, options=options)
            observations_list.append(dict(obs))
            infos_list.append(dict(infos))
        return observations_list, infos_list

    def step(
        self,
        actions_list: list[dict[str, Any]],
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, float]],
        list[dict[str, bool]],
        list[dict[str, bool]],
        list[dict[str, Any]],
    ]:
        """
        Step all envs. actions_list[i] is the action dict for env i (agent_id -> action).
        Returns (observations_list, rewards_list, terminations_list, truncations_list,
        infos_list).
        """
        if len(actions_list) != self._num_envs:
            raise ValueError(f"actions_list length {len(actions_list)} != num_envs {self._num_envs}")
        observations_list: list[dict[str, Any]] = []
        rewards_list: list[dict[str, float]] = []
        terminations_list: list[dict[str, bool]] = []
        truncations_list: list[dict[str, bool]] = []
        infos_list: list[dict[str, Any]] = []
        for env, actions in zip(self._envs, actions_list):
            obs, rewards, terms, truncs, infos = env.step(actions)
            observations_list.append(dict(obs))
            rewards_list.append(dict(rewards))
            terminations_list.append(dict(terms))
            truncations_list.append(dict(truncs))
            infos_list.append(dict(infos))
        return (
            observations_list,
            rewards_list,
            terminations_list,
            truncations_list,
            infos_list,
        )

    @property
    def agents(self) -> list[str]:
        """Agent list of the first env (all envs share the same layout)."""
        return list(self._envs[0].agents) if self._envs else []

    def close(self) -> None:
        for env in self._envs:
            env.close()

    async def reset_async(
        self,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Async reset: run sync reset in thread pool. Same return shape as reset()."""
        return await asyncio.to_thread(self.reset, seed=seed, options=options)

    async def step_async(
        self,
        actions_list: list[dict[str, Any]],
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, float]],
        list[dict[str, bool]],
        list[dict[str, bool]],
        list[dict[str, Any]],
    ]:
        """Async step: run sync step in thread pool. Same return shape as step()."""
        return await asyncio.to_thread(self.step, actions_list)


class AsyncLabTrustVectorEnv:
    """
    Like LabTrustVectorEnv but runs reset() and step() in parallel using a thread pool.
    Same API: reset(seed, options) and step(actions_list) return the same shapes.
    Each env still has its own seed (base_seed + env_index). Use when step() releases
    the GIL (e.g. numpy) to overlap work across envs. max_workers defaults to num_envs;
    tune for your workload. See design_choices.md 10.1.
    """

    def __init__(
        self,
        num_envs: int,
        *,
        base_seed: int = 0,
        env_factory: Any = None,
        max_workers: int | None = None,
        **kwargs: Any,
    ) -> None:
        self._num_envs = num_envs
        self._base_seed = base_seed
        self._max_workers = max_workers if max_workers is not None else num_envs
        if env_factory is not None and callable(env_factory):
            self._envs = [env_factory() for _ in range(num_envs)]
        else:
            self._envs = [LabTrustParallelEnv(**kwargs) for _ in range(num_envs)]
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)

    @property
    def num_envs(self) -> int:
        return self._num_envs

    def reset(
        self,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        base = seed if seed is not None else self._base_seed

        def _reset(i: int):
            env = self._envs[i]
            obs, infos = env.reset(seed=base + i, options=options)
            return i, dict(obs), dict(infos)

        results: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
        futs = [self._executor.submit(_reset, i) for i in range(self._num_envs)]
        for fut in as_completed(futs):
            results.append(fut.result())
        results.sort(key=lambda r: r[0])
        observations_list = [r[1] for r in results]
        infos_list = [r[2] for r in results]
        return observations_list, infos_list

    def step(
        self,
        actions_list: list[dict[str, Any]],
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, float]],
        list[dict[str, bool]],
        list[dict[str, bool]],
        list[dict[str, Any]],
    ]:
        if len(actions_list) != self._num_envs:
            raise ValueError(f"actions_list length {len(actions_list)} != num_envs {self._num_envs}")

        def _step(i: int):
            env = self._envs[i]
            obs, rewards, terms, truncs, infos = env.step(actions_list[i])
            return i, dict(obs), dict(rewards), dict(terms), dict(truncs), dict(infos)

        results_list: list[tuple[int, dict, dict, dict, dict, dict]] = []
        futs = [self._executor.submit(_step, i) for i in range(self._num_envs)]
        for fut in as_completed(futs):
            results_list.append(fut.result())
        results_list.sort(key=lambda r: r[0])
        observations_list = [r[1] for r in results_list]
        rewards_list = [r[2] for r in results_list]
        terminations_list = [r[3] for r in results_list]
        truncations_list = [r[4] for r in results_list]
        infos_list = [r[5] for r in results_list]
        return (
            observations_list,
            rewards_list,
            terminations_list,
            truncations_list,
            infos_list,
        )

    @property
    def agents(self) -> list[str]:
        return list(self._envs[0].agents) if self._envs else []

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        for env in self._envs:
            env.close()
