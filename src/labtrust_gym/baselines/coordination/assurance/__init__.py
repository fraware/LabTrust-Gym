"""
Coordination-layer runtime assurance: Simplex-style shield and safe fallback;
LLM detector throttle advisor wrapper.

- validate_plan: check route against collisions, restricted edges, RBAC.
- select_controller: choose advanced or fallback route based on shield result.
- wrap_with_simplex_shield: wrap an advanced method with shield + fallback.
- wrap_with_detector_advisor: wrap with LLM detector (detect + recommend; policy-validated containment).
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
from labtrust_gym.baselines.coordination.assurance.detector_advisor import (
    DeterministicDetectorBackend,
    wrap_with_detector_advisor,
)

__all__ = [
    "EMIT_COORD_SHIELD_DECISION",
    "REASON_SHIELD_COLLISION",
    "REASON_SHIELD_RBAC",
    "REASON_SHIELD_RESTRICTED",
    "select_controller",
    "validate_plan",
    "wrap_with_simplex_shield",
    "DeterministicDetectorBackend",
    "wrap_with_detector_advisor",
]
