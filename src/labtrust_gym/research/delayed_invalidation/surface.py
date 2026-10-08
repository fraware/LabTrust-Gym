"""Frozen synthetic scientific surface for the v0.1 preregistered study."""

from __future__ import annotations

import math


def benchmark_ph_surface(x: float) -> float:
    """Return hidden true pH for x in [0, 1].

    This is a deterministic benchmark surface. It is not presented as a
    chemically realistic formulation model.
    """
    if not 0.0 <= x <= 1.0:
        raise ValueError("x must lie in [0, 1]")
    return 7.0 + 1.20 * math.sin(2.0 * math.pi * x) + 0.35 * math.cos(6.0 * math.pi * x) + 0.25 * x


def benchmark_utility(x: float, *, target_ph: float = 7.40) -> float:
    """Utility maximized by the adaptive policy."""
    true_ph = benchmark_ph_surface(x)
    return -((true_ph - target_ph) ** 2)
