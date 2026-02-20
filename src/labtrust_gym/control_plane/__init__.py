"""
Control-plane: gate decisions and enforcement for the engine.

Runs first gates (RBAC, capability, signature) before mutation and post-step
enforcement (throttle, kill_switch, etc.). ControlPlane.apply(event, context)
returns a gate decision; apply_enforcement runs after the step. Keeps
authorization and enforcement in one place without changing the step result contract.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from labtrust_gym.control_plane.gates import apply_gates
from labtrust_gym.control_plane.interface import (
    ControlPlane,
    GateDecision,
)
from labtrust_gym.engine import enforcement as enforcement_module

# Re-export engine modules for clear boundary (control-plane owns these concepts)
from labtrust_gym.engine import rbac as rbac_module
from labtrust_gym.engine import signatures as signatures_module
from labtrust_gym.engine import tokens_runtime as tokens_runtime_module


def apply_enforcement_post_step(
    event: dict[str, Any],
    violations: list[dict[str, Any]],
    engine: Any | None,
    audit_callback: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Route post-step enforcement through control-plane. Delegates to engine.enforcement.apply_enforcement."""
    return enforcement_module.apply_enforcement(event, violations, engine, audit_callback)


__all__ = [
    "ControlPlane",
    "GateDecision",
    "apply_gates",
    "apply_enforcement_post_step",
    "rbac_module",
    "signatures_module",
    "enforcement_module",
    "tokens_runtime_module",
]
