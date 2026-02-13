"""
Concrete adapter that wraps the engine used by pz_parallel (CoreEnv).

Implements LabTrustEnvAdapter (reset, step, query) by delegating to CoreEnv.
Used as the default adapter in deterministic mode when no adapter is provided.
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.engine.event import StepEventDict
from labtrust_gym.engine.state import InitialStateDict
from labtrust_gym.runner.adapter import LabTrustEnvAdapter


class PZParallelAdapter(LabTrustEnvAdapter):
    """
    Adapter that wraps the same engine as LabTrustParallelEnv (CoreEnv).

    Implements reset, step, query by delegating to a CoreEnv instance.
    Use as the default when running the golden suite or deterministic runner.
    """

    def __init__(self) -> None:
        from labtrust_gym.engine.core_env import CoreEnv
        self._engine = CoreEnv()

    def reset(
        self,
        initial_state: InitialStateDict | dict[str, Any],
        *,
        deterministic: bool,
        rng_seed: int,
    ) -> None:
        self._engine.reset(
            initial_state,
            deterministic=deterministic,
            rng_seed=rng_seed,
        )

    def step(self, event: StepEventDict | dict[str, Any]) -> dict[str, Any]:
        return self._engine.step(event)

    def query(self, expr: str) -> Any:
        return self._engine.query(expr)
