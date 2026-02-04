"""
Coordination-layer runtime assurance: Simplex-style shield and safe fallback.

- validate_plan: check route against collisions, restricted edges, RBAC.
- select_controller: choose advanced or fallback route based on shield result.
- wrap_with_simplex_shield: wrap an advanced method with shield + fallback.
"""

from labtrust_gym.baselines.coordination.assurance.simplex import (
    EMIT_COORD_SHIELD_DECISION,
    REASON_SHIELD_COLLISION,
    REASON_SHIELD_RBAC,
    REASON_SHIELD_RESTRICTED,
    select_controller,
    validate_plan,
    wrap_with_simplex_shield,
)

__all__ = [
    "EMIT_COORD_SHIELD_DECISION",
    "REASON_SHIELD_COLLISION",
    "REASON_SHIELD_RBAC",
    "REASON_SHIELD_RESTRICTED",
    "select_controller",
    "validate_plan",
    "wrap_with_simplex_shield",
]
