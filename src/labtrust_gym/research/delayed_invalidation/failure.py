"""Failure schedules for the delayed-evidence-invalidation benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DriftKind(StrEnum):
    """Registered drift families."""

    OFFSET = "offset"
    SLOPE = "slope"


@dataclass(frozen=True)
class DriftSchedule:
    """Primary gradual drift schedule.

    v0.1 primary analysis uses OFFSET drift. SLOPE is reserved for the
    preregistered secondary ablation and requires an explicitly frozen
    standardized mapping before slope-drift results are run.
    """

    onset_index: int
    rate_sigma_per_experiment: float
    sigma0: float
    kind: DriftKind = DriftKind.OFFSET
    direction: int = 1
    base_offset_ph: float = 0.0
    base_slope_pct: float = 100.0

    def __post_init__(self) -> None:
        if self.onset_index < 0:
            raise ValueError("onset_index must be non-negative")
        if self.rate_sigma_per_experiment < 0:
            raise ValueError("rate_sigma_per_experiment must be non-negative")
        if self.sigma0 <= 0:
            raise ValueError("sigma0 must be positive")
        if self.direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        if self.base_slope_pct <= 0:
            raise ValueError("base_slope_pct must be positive")

    def elapsed_drift_steps(self, experiment_index: int) -> int:
        """Number of drift-bearing measurements at this experiment index."""
        if experiment_index < self.onset_index:
            return 0
        return experiment_index - self.onset_index + 1

    def offset_ph_at(self, experiment_index: int) -> float:
        """Physical offset for the registered offset-drift family."""
        if self.kind is not DriftKind.OFFSET:
            raise NotImplementedError(
                "Slope drift requires a separately frozen standardized mapping."
            )
        steps = self.elapsed_drift_steps(experiment_index)
        increment = self.direction * steps * self.rate_sigma_per_experiment * self.sigma0
        return self.base_offset_ph + increment

    def instrument_parameters_at(self, experiment_index: int) -> tuple[float, float]:
        """Return physical offset pH and physical slope percent."""
        if self.kind is DriftKind.OFFSET:
            return self.offset_ph_at(experiment_index), self.base_slope_pct
        raise NotImplementedError(
            "Slope drift is a preregistered secondary ablation, not part of the v0.1 primary implementation."
        )
