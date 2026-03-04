"""
Minimal CoordinationMethod for the extension example: returns NOOP for all agents.

Demonstrates reuse for coord-only extensions (no new task). Use with an existing
task (e.g. coord_scale) via --coord-method example_noop_coord.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.baselines.coordination.interface import (
    CoordinationMethod,
)
from labtrust_gym.envs.action_contract import ACTION_NOOP


class ExampleNoopCoord(CoordinationMethod):
    """Minimal coord method: all agents get NOOP every step."""

    @property
    def method_id(self) -> str:
        return "example_noop_coord"

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agents = sorted(obs.keys())
        return {aid: {"action_index": ACTION_NOOP, "action_type": "NOOP"} for aid in agents}


def factory(
    policy: dict[str, Any],
    repo_root: Path | None,
    scale_config_override: dict[str, Any] | None,
    default_params: dict[str, Any],
) -> CoordinationMethod:
    """Factory for the coordination method (required by the registry contract)."""
    return ExampleNoopCoord()
