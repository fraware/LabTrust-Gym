"""
Resilience scoring: when a metric is missing, missing_metric_behavior (zero, one, omit)
determines how the component score is computed.
"""

from __future__ import annotations

from labtrust_gym.studies.resilience_scoring import (
    compute_components,
    compute_resilience_score,
)


def _minimal_policy(missing_metric_behavior: str) -> dict:
    return {
        "weights": {
            "perf": 0.25,
            "safety": 0.25,
            "security": 0.25,
            "coordination": 0.25,
        },
        "missing_metric_behavior": missing_metric_behavior,
        "components": {
            "perf": {
                "sub_metrics": {
                    "throughput": {
                        "cell_key": "perf.throughput",
                        "direction": "higher_better",
                        "range": [0, 50],
                    },
                },
            },
            "safety": {"sub_metrics": {}},
            "security": {"sub_metrics": {}},
            "coordination": {"sub_metrics": {}},
        },
    }


def test_missing_metric_omit() -> None:
    """omit: missing metric excluded from component; component = 0.5 when no sub-metrics present."""
    policy = _minimal_policy("omit")
    cell_metrics = {}  # no metrics
    components = compute_components(cell_metrics, policy)
    assert components["component_perf"] == 0.5
    assert components["component_safety"] == 0.5
    assert components["component_security"] == 0.5
    assert components["component_coordination"] == 0.5


def test_missing_metric_zero() -> None:
    """zero: missing metric treated as 0; component perf has one sub-metric so only throughput; when missing, score 0."""
    policy = _minimal_policy("zero")
    cell_metrics = {}  # throughput missing
    components = compute_components(cell_metrics, policy)
    assert components["component_perf"] == 0.0
    assert components["component_safety"] == 0.5  # no sub_metrics, default 0.5
    score = compute_resilience_score(components, policy["weights"])
    assert 0.0 <= score <= 1.0


def test_missing_metric_one() -> None:
    """one: missing metric treated as 1."""
    policy = _minimal_policy("one")
    cell_metrics = {}
    components = compute_components(cell_metrics, policy)
    assert components["component_perf"] == 1.0
    score = compute_resilience_score(components, policy["weights"])
    assert score >= 0.5


def test_partial_metrics_omit() -> None:
    """omit: only present metrics contribute; one present => component is that score."""
    policy = _minimal_policy("omit")
    cell_metrics = {"perf.throughput": 25.0}  # mid-range: (25-0)/50 = 0.5
    components = compute_components(cell_metrics, policy)
    assert components["component_perf"] == 0.5
    assert components["component_safety"] == 0.5
