"""
Control-plane: coordination decisions, RBAC, tokens, signatures, enforcement, audit.

Narrow interface: ControlPlane.apply(event, context) -> gate_decision + enforcement_actions.
First gates (RBAC, capability, signature) and post-step enforcement flow through here.
Does not modify results contract; refactor is incremental.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from labtrust_gym.control_plane.interface import (
    ControlPlane,
    GateDecision,
)
from labtrust_gym.control_plane.gates import apply_gates

# Re-export engine modules for clear boundary (control-plane owns these concepts)
from labtrust_gym.engine import rbac as rbac_module
from labtrust_gym.engine import signatures as signatures_module
from labtrust_gym.engine import enforcement as enforcement_module
from labtrust_gym.engine import tokens_runtime as tokens_runtime_module


def apply_enforcement_post_step(
    event: Dict[str, Any],
    violations: List[Dict[str, Any]],
    engine: Optional[Any],
    audit_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> List[Dict[str, Any]]:
    """Route post-step enforcement through control-plane. Delegates to engine.enforcement.apply_enforcement."""
    return enforcement_module.apply_enforcement(
        event, violations, engine, audit_callback
    )


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
