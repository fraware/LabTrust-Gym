"""
Tests for learning-to-bid: determinism, checksum, calibration MAE.
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.coordination.allocation.learning_to_bid import (
    MinimalRegressor,
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


def test_learning_to_bid_training_determinism() -> None:
    """Same seed and same data -> same model checksum (MinimalRegressor)."""
    buffer = [
        {"agent_id": "a1", "work_id": "W1", "device_id": "D1", "observed_cost": 0.3},
        {"agent_id": "a1", "work_id": "W2", "device_id": "D1", "observed_cost": 0.5},
    ]
    r1 = MinimalRegressor(seed=42)
    r1.fit(buffer)
    c1 = r1.get_checksum()
    r2 = MinimalRegressor(seed=42)
    r2.fit(buffer)
    c2 = r2.get_checksum()
    assert c1 == c2, "Two training runs with same seed and data must yield same checksum"
    r3 = MinimalRegressor(seed=99)
    r3.fit(buffer)
    assert r3.get_checksum() != c1


def test_calibration_mae_decreases_with_more_data() -> None:
    """Predicted vs observed error decreases over epochs as buffer grows (MinimalRegressor)."""
    def pred_from_fit(agent_id: str, work_id: str, device_id: str, buf: list) -> float:
        r = MinimalRegressor(seed=42)
        r.fit(buf)
        return r.predict(agent_id, work_id, device_id)

    buffer_small = [
        {"agent_id": "a1", "work_id": "W1", "device_id": "D1", "observed_cost": 0.1},
        {"agent_id": "a1", "work_id": "W2", "device_id": "D1", "observed_cost": 0.9},
    ]
    buffer_large = buffer_small + [
        {"agent_id": "a1", "work_id": "W1", "device_id": "D1", "observed_cost": 0.5},
        {"agent_id": "a1", "work_id": "W2", "device_id": "D1", "observed_cost": 0.5},
        {"agent_id": "a1", "work_id": "W1", "device_id": "D1", "observed_cost": 0.5},
    ]
    mae_small = calibration_mae(buffer_small, predict_fn=pred_from_fit)
    mae_large = calibration_mae(buffer_large, predict_fn=pred_from_fit)
    assert mae_large <= mae_small + 1e-6, "More data should reduce or maintain MAE"


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
