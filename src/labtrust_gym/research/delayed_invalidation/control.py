"""Measurement-control primitives for delayed invalidation studies.

This module owns only the registered check-standard rule and suspect interval.
It does not perform scientific-state recovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class CheckStandardResult:
    """One scheduled check-standard decision."""

    experiment_index: int
    reference_ph: float
    readings: tuple[float, ...]
    mean_reported_ph: float
    threshold_ph: float
    in_control: bool


@dataclass(frozen=True)
class SuspectInterval:
    """Conservative interval supplied to non-oracle recovery methods."""

    last_in_control_index: int
    detection_index: int

    def contains(self, experiment_index: int) -> bool:
        return self.last_in_control_index < experiment_index <= self.detection_index


def evaluate_check_standard(
    readings: Iterable[float],
    *,
    experiment_index: int,
    sigma0: float,
    reference_ph: float = 7.0,
) -> CheckStandardResult:
    """Apply the preregistered 3-sigma mean check rule."""
    values = tuple(float(v) for v in readings)
    if not values:
        raise ValueError("readings must be non-empty")
    if sigma0 <= 0:
        raise ValueError("sigma0 must be positive")
    mean_value = float(np.mean(np.asarray(values, dtype=float)))
    threshold = 3.0 * sigma0 / sqrt(len(values))
    return CheckStandardResult(
        experiment_index=int(experiment_index),
        reference_ph=float(reference_ph),
        readings=values,
        mean_reported_ph=mean_value,
        threshold_ph=float(threshold),
        in_control=abs(mean_value - reference_ph) <= threshold,
    )


def suspect_interval_from_history(
    history: Iterable[CheckStandardResult],
) -> SuspectInterval | None:
    """Return the first detected out-of-control interval from ordered checks.

    A detection requires at least one previous in-control check. If the first
    check is already out of control, the conservative onset is unresolved and
    this function returns None rather than inventing a prior boundary.
    """
    ordered = sorted(history, key=lambda item: item.experiment_index)
    last_good: CheckStandardResult | None = None
    for result in ordered:
        if result.in_control:
            last_good = result
            continue
        if last_good is None:
            return None
        return SuspectInterval(
            last_in_control_index=last_good.experiment_index,
            detection_index=result.experiment_index,
        )
    return None
