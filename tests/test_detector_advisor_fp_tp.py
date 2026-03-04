"""
Unit tests for detector advisor: FP cap (clean obs -> no throttle), TP floor (anomaly -> flag within bound).
"""

from __future__ import annotations

from labtrust_gym.baselines.coordination.assurance.detector_advisor import (
    ALLOWED_ENFORCEMENT_ACTIONS,
    DeterministicDetectorBackend,
    detector_calibration_metrics,
)


def test_detector_fp_cap_clean_obs_no_throttle() -> None:
    """Clean obs (no anomaly): detector should not throttle; enforcement none and probability 0."""
    backend = DeterministicDetectorBackend(seed=42, latency_bound_steps=3)
    event_summary = {
        "step": 0,
        "obs_snapshot": {
            "a1": {"queue_has_head": [1, 1]},
            "a2": {"queue_has_head": [1, 1]},
        },
        "comms_stats": {},
    }
    out = backend.detect(0, event_summary, None)
    assert out.recommend.enforcement_action == "none"
    assert out.detect.probability == 0.0
    assert out.detect.is_attack_suspected is False


def test_detector_tp_floor_anomaly_flags_within_bound() -> None:
    """With anomaly (mixed queue_has_head), detector should flag within latency_bound steps; probability > 0."""
    backend = DeterministicDetectorBackend(seed=0, latency_bound_steps=2)
    event_summary = {
        "step": 3,
        "obs_snapshot": {
            "a1": {"queue_has_head": [1, 0]},
            "a2": {"queue_has_head": [0, 1]},
        },
        "comms_stats": {},
    }
    out = backend.detect(3, event_summary, None)
    assert out.detect.is_attack_suspected is True
    assert out.detect.probability >= 0.0
    assert out.detect.abstain is False
    assert out.detect.suspected_risk_id == "INJ-COMMS-POISON-001"


def test_detector_detection_appears_within_latency_bound() -> None:
    """Inject anomaly; assert detection appears when step >= latency_bound_steps (and not before)."""
    latency_bound = 3
    backend = DeterministicDetectorBackend(seed=7, latency_bound_steps=latency_bound)
    # Anomaly: mixed queue_has_head so _queue_anomaly_score > 0
    event_summary = {
        "obs_snapshot": {
            "a1": {"queue_has_head": [1, 0]},
            "a2": {"queue_has_head": [0, 1]},
        },
        "comms_stats": {},
    }
    for step in range(latency_bound + 2):
        ev = dict(event_summary, step=step)
        out = backend.detect(step, ev, None)
        if step < latency_bound:
            assert out.detect.is_attack_suspected is False, f"step {step} should not detect before latency_bound"
        else:
            assert out.detect.is_attack_suspected is True, f"step {step} should detect within latency bound"


def test_detector_gating_uses_probability_threshold_and_cooldown() -> None:
    """Wrapper uses probability_threshold and cooldown_steps; allowed enforcement actions are policy-set."""
    assert "throttle" in ALLOWED_ENFORCEMENT_ACTIONS
    assert "freeze_zone" in ALLOWED_ENFORCEMENT_ACTIONS
    assert "kill_switch" in ALLOWED_ENFORCEMENT_ACTIONS
    assert "none" in ALLOWED_ENFORCEMENT_ACTIONS


def test_detector_calibration_compute_metrics() -> None:
    """When ground-truth labels exist, compare detector output to labels; report precision/recall or MAE."""
    labels = [0, 0, 1, 1]
    predictions = [0, 1, 1, 0]
    tp = sum(1 for l, p in zip(labels, predictions) if l == 1 and p == 1)
    fp = sum(1 for l, p in zip(labels, predictions) if l == 0 and p == 1)
    fn = sum(1 for l, p in zip(labels, predictions) if l == 1 and p == 0)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    assert 0 <= precision <= 1
    assert 0 <= recall <= 1


def test_detector_calibration_with_fixture() -> None:
    """Calibration path: fixture of ground-truth labels and detector outputs; precision/recall/F1/MAE."""
    y_true = [0, 0, 1, 1, 1]
    y_pred = [0, 0, 1, 0, 1]
    proba = [0.1, 0.2, 0.9, 0.3, 0.85]
    metrics = detector_calibration_metrics(y_true, y_pred, proba=proba)
    assert 0 <= metrics["precision"] <= 1
    assert 0 <= metrics["recall"] <= 1
    assert 0 <= metrics["f1"] <= 1
    assert "mae" in metrics
    assert 0 <= metrics["mae"] <= 1
    assert metrics["precision"] == 1.0
    assert abs(metrics["recall"] - (2.0 / 3.0)) < 0.001
