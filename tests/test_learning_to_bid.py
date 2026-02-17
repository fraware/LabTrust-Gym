"""
Tests for learning-to-bid: determinism, checksum, calibration MAE.
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.coordination.allocation.learning_to_bid import (
    calibration_mae,
    predict_cost,
    predict_cost_checksum,
)


def test_predict_cost_determinism() -> None:
    """Same args and buffer -> same prediction across two calls."""
    buffer = [{"seed": 42}, {"observed_cost": 1.0}]
    v1 = predict_cost("a1", "W1", "D1", buffer)
    v2 = predict_cost("a1", "W1", "D1", buffer)
    assert v1 == v2


def test_predict_cost_checksum_determinism() -> None:
    """Same (agent_id, work_id, device_id, buffer_len, seed) -> same checksum."""
    c1 = predict_cost_checksum("a1", "W1", "D1", 5, 42)
    c2 = predict_cost_checksum("a1", "W1", "D1", 5, 42)
    assert c1 == c2
    c3 = predict_cost_checksum("a1", "W1", "D1", 5, 99)
    assert c1 != c3


def test_calibration_mae_deterministic_and_non_negative() -> None:
    """Calibration MAE is non-negative, finite, and deterministic for same buffer."""
    buf1 = [
        {"agent_id": "a1", "work_id": "W1", "device_id": "D1", "observed_cost": 0.5, "seed": 1},
    ]
    buf2 = buf1 + [
        {"agent_id": "a1", "work_id": "W2", "device_id": "D1", "observed_cost": 0.6, "seed": 1},
    ]
    mae1 = calibration_mae(buf1)
    mae2 = calibration_mae(buf2)
    assert mae1 >= 0 and mae2 >= 0
    assert isinstance(mae1, (int, float)) and isinstance(mae2, (int, float))
    assert calibration_mae(buf1) == mae1 and calibration_mae(buf2) == mae2
