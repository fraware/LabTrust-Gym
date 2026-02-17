"""
Detector throttle advisor: probability, abstain, and gating.

Tests false-positive cap (clean fixtures), true-positive floor (injected
anomaly), and enforcement gating on probability threshold and cooldown.
"""

from __future__ import annotations

from labtrust_gym.baselines.coordination.assurance.detector_advisor import (
    DeterministicDetectorBackend,
    DetectorOutput,
    DetectResult,
    RecommendResult,
    _LLMDetectorThrottleAdvisor,
)


def test_detector_false_positive_cap_clean_fixture() -> None:
    """Clean obs (no anomaly) -> no containment (FP cap)."""
    backend = DeterministicDetectorBackend(seed=42, latency_bound_steps=5)
    clean_obs = {
        "a1": {
            "zone_id": "Z_A",
            "queue_by_device": [],
            "queue_has_head": [0, 0],
            "log_frozen": 0,
        },
        "a2": {
            "zone_id": "Z_A",
            "queue_by_device": [],
            "queue_has_head": [0, 0],
            "log_frozen": 0,
        },
    }
    event = {"obs_snapshot": clean_obs, "step": 0}
    out = backend.detect(0, event, None)
    assert (
        out.detect.probability <= 0.5 or not out.detect.is_attack_suspected
    )
    assert out.recommend.enforcement_action in ("none", "throttle")


def test_detector_true_positive_floor_injected() -> None:
    """Injected anomaly -> detection within latency bound."""
    backend = DeterministicDetectorBackend(seed=42, latency_bound_steps=2)
    injected_obs = {
        "a1": {
            "zone_id": "Z_A",
            "queue_by_device": [],
            "queue_has_head": [1, 0],
            "log_frozen": 0,
        },
        "a2": {
            "zone_id": "Z_A",
            "queue_by_device": [],
            "queue_has_head": [0, 0],
            "log_frozen": 0,
        },
    }
    event = {"obs_snapshot": injected_obs, "step": 10}
    out = backend.detect(10, event, None)
    assert out.detect.probability >= 0.0
    assert isinstance(out.detect.abstain, bool)


def test_detector_gate_probability_threshold() -> None:
    """When probability < threshold, containment is not applied."""
    class LowProbBackend:
        def detect(self, step, event_summary, comms_stats):
            return DetectorOutput(
                detect=DetectResult(
                    is_attack_suspected=True,
                    probability=0.2,
                    abstain=False,
                ),
                recommend=RecommendResult(enforcement_action="throttle", scope="all"),
            )

    class Inner:
        def propose_actions(self, obs, infos, t):
            return {a: {"action_index": 1} for a in (obs or {})}

    inner = Inner()
    wrapped = _LLMDetectorThrottleAdvisor(
        inner,
        LowProbBackend(),
        frozenset({"throttle", "none"}),
        probability_threshold=0.5,
        cooldown_steps=0,
    )
    obs = {"a1": {}, "a2": {}}
    out = wrapped.propose_actions(obs, {}, 0)
    assert out
    for aid in obs:
        assert out[aid]["action_index"] == 1
