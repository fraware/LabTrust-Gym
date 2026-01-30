"""
Deterministic RNG wrapper for simulation.

Single RNG used for all sampling (service times, failures, etc.).
Seeded from scenario so same seed + actions => same outcomes.
"""

from __future__ import annotations

import random
from typing import Optional


class RNG:
    """
    Deterministic RNG. Use this instead of random.* for all simulation sampling.
    """

    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)

    def seed(self, seed: int) -> None:
        self._rng.seed(seed)

    def random(self) -> float:
        return self._rng.random()

    def randint(self, a: int, b: int) -> int:
        return self._rng.randint(a, b)

    def uniform(self, a: float, b: float) -> float:
        return self._rng.uniform(a, b)

    def sample_service_time_deterministic_s(self, value_s: float) -> float:
        """Return fixed value (for dist: deterministic)."""
        return float(value_s)

    def sample_service_time_uniform_s(
        self,
        low_s: float,
        high_s: float,
    ) -> float:
        """Sample service time from uniform(low_s, high_s)."""
        return self._rng.uniform(low_s, high_s)

    def sample_lognormal_s(self, mu: float, sigma: float) -> float:
        """Sample from lognormal(mu, sigma); result in seconds (e.g. MTTR)."""
        import math
        z = self._rng.gauss(0.0, 1.0)
        return float(math.exp(mu + sigma * z))
