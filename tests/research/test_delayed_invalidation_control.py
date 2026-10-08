from __future__ import annotations

import pytest

from labtrust_gym.research.delayed_invalidation.control import (
    evaluate_check_standard,
    suspect_interval_from_history,
)


def test_check_standard_accepts_reference_centered_readings() -> None:
    result = evaluate_check_standard(
        [7.001, 6.999, 7.000, 7.002, 6.998],
        experiment_index=20,
        sigma0=0.01,
    )
    assert result.in_control


def test_check_standard_rejects_mean_beyond_registered_threshold() -> None:
    result = evaluate_check_standard(
        [7.03, 7.03, 7.03, 7.03, 7.03],
        experiment_index=40,
        sigma0=0.01,
    )
    assert not result.in_control
    assert result.threshold_ph == pytest.approx(3.0 * 0.01 / (5.0**0.5))


def test_suspect_interval_uses_last_good_check_and_first_failure() -> None:
    good_20 = evaluate_check_standard(
        [7.0] * 5,
        experiment_index=20,
        sigma0=0.01,
    )
    good_40 = evaluate_check_standard(
        [7.0] * 5,
        experiment_index=40,
        sigma0=0.01,
    )
    bad_60 = evaluate_check_standard(
        [7.03] * 5,
        experiment_index=60,
        sigma0=0.01,
    )
    interval = suspect_interval_from_history([bad_60, good_20, good_40])
    assert interval is not None
    assert interval.last_in_control_index == 40
    assert interval.detection_index == 60
    assert not interval.contains(40)
    assert interval.contains(41)
    assert interval.contains(60)


def test_first_check_failure_does_not_invent_last_good_boundary() -> None:
    bad = evaluate_check_standard(
        [7.03] * 5,
        experiment_index=20,
        sigma0=0.01,
    )
    assert suspect_interval_from_history([bad]) is None
