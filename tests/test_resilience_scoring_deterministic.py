"""
Resilience scoring: same cell_metrics and policy yield same components and score.
Changing weights in policy changes score deterministically.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.studies.resilience_scoring import (
    compute_components,
    compute_resilience_score,
    load_resilience_scoring_policy,
)


def test_same_input_same_output() -> None:
    """Same cell_metrics and policy => identical components and resilience_score."""
    policy = {
        "weights": {
            "perf": 0.25,
            "safety": 0.25,
            "security": 0.25,
            "coordination": 0.25,
        },
        "missing_metric_behavior": "omit",
        "components": {
            "perf": {
                "sub_metrics": {
                    "throughput": {
                        "cell_key": "perf.throughput",
                        "direction": "higher_better",
                        "range": [0, 50],
                    },
                    "p95_tat": {
                        "cell_key": "perf.p95_tat",
                        "direction": "lower_better",
                        "range": [0, 600],
                    },
                },
            },
            "safety": {
                "sub_metrics": {
                    "violations_total": {
                        "cell_key": "safety.violations_total",
                        "direction": "lower_better",
                        "range": [0, 100],
                    },
                },
            },
            "security": {"sub_metrics": {}},
            "coordination": {"sub_metrics": {}},
        },
    }
    cell_metrics = {
        "perf.throughput": 20.0,
        "perf.p95_tat": 200.0,
        "safety.violations_total": 5,
    }
    c1 = compute_components(cell_metrics, policy)
    c2 = compute_components(cell_metrics, policy)
    assert c1 == c2
    w = policy["weights"]
    s1 = compute_resilience_score(c1, w)
    s2 = compute_resilience_score(c2, w)
    assert s1 == s2


def test_changing_weights_changes_score() -> None:
    """Different weights => different resilience_score for same components."""
    components = {
        "component_perf": 0.8,
        "component_safety": 0.2,
        "component_security": 0.5,
        "component_coordination": 0.6,
    }
    w1 = {"perf": 0.5, "safety": 0.2, "security": 0.15, "coordination": 0.15}
    w2 = {"perf": 0.2, "safety": 0.5, "security": 0.15, "coordination": 0.15}
    score1 = compute_resilience_score(components, w1)
    score2 = compute_resilience_score(components, w2)
    assert score1 != score2
    assert 0.0 <= score1 <= 1.0
    assert 0.0 <= score2 <= 1.0


def test_load_policy_smoke(repo_root: Path) -> None:
    """Load default policy from repo; weights sum to 1 and components exist."""
    policy_path = repo_root / "policy" / "coordination" / "resilience_scoring.v0.1.yaml"
    if not policy_path.exists():
        pytest.skip("resilience_scoring.v0.1.yaml not found")
    policy = load_resilience_scoring_policy(policy_path)
    w = policy.get("weights") or {}
    total = sum(w.get(k, 0) for k in ("perf", "safety", "security", "coordination"))
    assert abs(total - 1.0) < 0.01
    assert "perf" in policy.get("components", {})
    assert "safety" in policy.get("components", {})


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent
