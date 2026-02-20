"""
Deterministic RNG wrapper for simulation.

Single RNG used for all sampling (service times, failures, etc.).
Seeded from scenario so same seed + actions => same outcomes.

Algorithm: Python's random.Random (Mersenne Twister). Determinism is guaranteed
for the same Python version and seed; cross-version reproducibility is not
guaranteed by the language. Use the same Python version as the baseline when
comparing hashes or running the determinism report.
"""

from __future__ import annotations

import random

# For determinism contract (same algorithm as task get_initial_state).
RNG_ALGORITHM = "random.Random (Mersenne Twister)"


class RNG:
    """
    Deterministic RNG. Use this instead of random.* for all simulation sampling.
    Seeded per episode (base_seed + episode index) so no global state.
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
        """Sample from lognormal(mu, sigma); result in seconds (e.g. mean time to repair)."""
        import math

        z = self._rng.gauss(0.0, 1.0)
        return float(math.exp(mu + sigma * z))
