"""Unit tests for detector calibration (ECE, MCE, calibration_curve_bins)."""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.coordination.assurance.detector_advisor import (
    calibration_curve_bins,
    detector_calibration_metrics,
    expected_calibration_error,
    maximum_calibration_error,
)


class TestExpectedCalibrationError:
    def test_perfectly_calibrated_zero_ece(self) -> None:
        # One bin with many samples: mean proba = 0.5, accuracy = 0.5 -> ECE = 0
        proba = [0.5] * 10
        y_true = [0] * 5 + [1] * 5
        assert expected_calibration_error(proba, y_true, n_bins=2) == 0.0

    def test_miscalibrated_positive_ece(self) -> None:
        # All predict 0.5 but half are 0 half are 1 -> acc in bin = 0.5, mean_prob = 0.5 -> 0; need clear miscalibration
        proba = [0.9, 0.9, 0.9, 0.1, 0.1, 0.1]
        y_true = [0, 0, 0, 1, 1, 1]  # low prob when 1, high when 0
        ece = expected_calibration_error(proba, y_true, n_bins=10)
        assert ece > 0.5

    def test_empty_returns_zero(self) -> None:
        assert expected_calibration_error([], [], n_bins=10) == 0.0

    def test_length_mismatch_returns_zero(self) -> None:
        assert expected_calibration_error([0.5], [0, 1], n_bins=10) == 0.0


class TestMaximumCalibrationError:
    def test_perfectly_calibrated_zero_mce(self) -> None:
        # One bin: mean proba = 0.5, accuracy = 0.5
        proba = [0.5] * 4
        y_true = [0, 0, 1, 1]
        assert maximum_calibration_error(proba, y_true, n_bins=2) == 0.0

    def test_mce_at_least_ece(self) -> None:
        proba = [0.9] * 3 + [0.1] * 3
        y_true = [0, 0, 0, 1, 1, 1]
        ece = expected_calibration_error(proba, y_true, n_bins=10)
        mce = maximum_calibration_error(proba, y_true, n_bins=10)
        assert mce >= ece

    def test_empty_returns_zero(self) -> None:
        assert maximum_calibration_error([], [], n_bins=10) == 0.0


class TestCalibrationCurveBins:
    def test_returns_three_lists(self) -> None:
        proba = [0.2, 0.5, 0.8]
        y_true = [0, 0, 1]
        means, accs, weights = calibration_curve_bins(proba, y_true, n_bins=5)
        assert isinstance(means, list)
        assert isinstance(accs, list)
        assert isinstance(weights, list)
        assert len(means) == len(accs) == len(weights)
        assert abs(sum(weights) - 1.0) < 1e-9 or sum(weights) == 0

    def test_empty_returns_empty_tuples(self) -> None:
        means, accs, weights = calibration_curve_bins([], [], n_bins=10)
        assert means == accs == weights == []


class TestDetectorCalibrationMetrics:
    def test_with_proba_adds_ece_mce(self) -> None:
        y_true = [0, 1, 0, 1]
        y_pred = [0, 1, 0, 1]
        proba = [0.1, 0.9, 0.2, 0.8]
        out = detector_calibration_metrics(y_true, y_pred, proba=proba)
        assert "ece" in out
        assert "mce" in out
        assert "mae" in out
        assert out["precision"] == 1.0 and out["recall"] == 1.0

    def test_without_proba_no_ece_mce(self) -> None:
        y_true = [0, 1, 0, 1]
        y_pred = [0, 1, 0, 1]
        out = detector_calibration_metrics(y_true, y_pred)
        assert "ece" not in out
        assert "mce" not in out
        assert "mae" not in out

    def test_known_miscalibration_ece_positive(self) -> None:
        # All proba=0.7, all y_true=0 -> in one bin acc=0, mean_prob=0.7 -> |0-0.7|=0.7
        y_true = [0, 0, 0]
        y_pred = [1, 1, 1]  # predict positive
        proba = [0.7, 0.7, 0.7]
        out = detector_calibration_metrics(y_true, y_pred, proba=proba)
        assert out["ece"] == pytest.approx(0.7, abs=0.01)
        assert out["mce"] == pytest.approx(0.7, abs=0.01)
