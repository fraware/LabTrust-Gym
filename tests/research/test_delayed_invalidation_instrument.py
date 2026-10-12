from __future__ import annotations

import math

import numpy as np
import pytest

from labtrust_gym.research.delayed_invalidation.failure import DriftKind, DriftSchedule
from labtrust_gym.research.delayed_invalidation.instrument import LadsAlignedPhMeter
from labtrust_gym.research.delayed_invalidation.surface import benchmark_ph_surface, benchmark_utility


def test_ideal_meter_reconstructs_true_ph_without_noise() -> None:
    meter = LadsAlignedPhMeter()
    for true_ph in (4.0, 6.5, 7.0, 9.25):
        measurement = meter.measure(true_ph, raw_noise_mv=0.0)
        assert measurement.reported_ph == pytest.approx(true_ph, abs=1e-12)


def test_physical_offset_with_stale_calibration_biases_reported_value() -> None:
    meter = LadsAlignedPhMeter()
    measurement = meter.measure(
        6.5,
        physical_offset_ph=0.20,
        calibration_offset_ph=0.0,
        raw_noise_mv=0.0,
    )
    assert measurement.reported_ph == pytest.approx(6.30, abs=1e-12)


def test_physical_slope_detuning_is_observable_with_stale_calibration() -> None:
    meter = LadsAlignedPhMeter()
    measurement = meter.measure(
        4.0,
        physical_slope_pct=95.0,
        calibration_slope_pct=100.0,
        raw_noise_mv=0.0,
    )
    assert measurement.reported_ph == pytest.approx(4.15, abs=1e-12)


def test_seeded_measurements_are_reproducible() -> None:
    meter = LadsAlignedPhMeter()
    rng_a = np.random.default_rng(1234)
    rng_b = np.random.default_rng(1234)
    seq_a = [meter.measure(7.0, rng=rng_a).reported_ph for _ in range(25)]
    seq_b = [meter.measure(7.0, rng=rng_b).reported_ph for _ in range(25)]
    assert seq_a == seq_b


def test_sigma0_is_positive_and_reproducible() -> None:
    meter = LadsAlignedPhMeter()
    sigma_a = meter.estimate_sigma0(seed=20261008, readings=1000)
    sigma_b = meter.estimate_sigma0(seed=20261008, readings=1000)
    assert sigma_a > 0.0
    assert sigma_a == pytest.approx(sigma_b, rel=0.0, abs=0.0)


def test_offset_drift_starts_exactly_at_registered_onset() -> None:
    schedule = DriftSchedule(
        onset_index=60,
        rate_sigma_per_experiment=0.125,
        sigma0=0.01,
        kind=DriftKind.OFFSET,
    )
    assert schedule.offset_ph_at(59) == pytest.approx(0.0)
    assert schedule.offset_ph_at(60) == pytest.approx(0.00125)
    assert schedule.offset_ph_at(61) == pytest.approx(0.00250)


def test_surface_contract() -> None:
    assert benchmark_ph_surface(0.0) == pytest.approx(7.35)
    assert math.isfinite(benchmark_ph_surface(0.5))
    assert benchmark_utility(0.25) <= 0.0
    with pytest.raises(ValueError):
        benchmark_ph_surface(-0.01)


def test_systematic_bias_matches_stale_offset_error() -> None:
    meter = LadsAlignedPhMeter()
    bias = meter.systematic_bias_ph(
        6.5,
        physical_offset_ph=0.20,
        calibration_offset_ph=0.0,
    )
    assert bias == pytest.approx(-0.20, abs=1e-12)
