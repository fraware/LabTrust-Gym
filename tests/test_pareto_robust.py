"""Unit tests for uncertainty-aware (robust) Pareto dominance."""

from __future__ import annotations

from labtrust_gym.benchmarks.pareto import (
    DEFAULT_OBJECTIVES,
    _pareto_dominates,
    _pareto_dominates_robust,
    _row_key,
    compute_nondominated_per_scale,
    compute_nondominated_per_scale_robust,
)


def test_row_key_stable() -> None:
    r = {"method_id": "m1", "scale_id": "s1", "injection_id": "inj1"}
    assert _row_key(r) == ("m1", "s1", "inj1")
    assert _row_key({}) == ("", "", "")


def test_pareto_dominates_robust_fallback_when_no_ci() -> None:
    """When row_to_ci is None, robust dominance equals point dominance."""
    a = {"method_id": "a", "scale_id": "s", "injection_id": "i", "perf.throughput": 10, "perf.p95_tat": 5}
    b = {"method_id": "b", "scale_id": "s", "injection_id": "i", "perf.throughput": 5, "perf.p95_tat": 10}
    objectives = [("perf.throughput", "max"), ("perf.p95_tat", "min")]
    assert _pareto_dominates(a, b, objectives) is True
    assert _pareto_dominates_robust(a, b, objectives, row_to_ci=None) is True


def test_pareto_dominates_robust_with_non_overlapping_ci() -> None:
    """When CIs do not overlap, robust dominance matches point dominance."""
    a = {"method_id": "a", "scale_id": "s", "injection_id": "i", "perf.throughput": 10, "perf.p95_tat": 5}
    b = {"method_id": "b", "scale_id": "s", "injection_id": "i", "perf.throughput": 5, "perf.p95_tat": 10}
    objectives = [("perf.throughput", "max"), ("perf.p95_tat", "min")]
    row_to_ci = {
        _row_key(a): {
            "perf.throughput": {"ci_low": 9, "ci_high": 11},
            "perf.p95_tat": {"ci_low": 4, "ci_high": 6},
        },
        _row_key(b): {
            "perf.throughput": {"ci_low": 4, "ci_high": 6},
            "perf.p95_tat": {"ci_low": 9, "ci_high": 11},
        },
    }
    assert _pareto_dominates_robust(a, b, objectives, row_to_ci) is True
    assert _pareto_dominates_robust(b, a, objectives, row_to_ci) is False


def test_pareto_dominates_robust_with_overlapping_ci() -> None:
    """When CIs overlap, robust dominance can say neither dominates."""
    a = {"method_id": "a", "scale_id": "s", "injection_id": "i", "perf.throughput": 10, "perf.p95_tat": 8}
    b = {"method_id": "b", "scale_id": "s", "injection_id": "i", "perf.throughput": 9, "perf.p95_tat": 7}
    # Point: a has higher throughput, b has lower p95 -> point dominance unclear (a better on throughput, b better on p95)
    objectives = [("perf.throughput", "max"), ("perf.p95_tat", "min")]
    # Make CIs overlap so neither clearly dominates
    row_to_ci = {
        _row_key(a): {
            "perf.throughput": {"ci_low": 8, "ci_high": 12},
            "perf.p95_tat": {"ci_low": 6, "ci_high": 10},
        },
        _row_key(b): {
            "perf.throughput": {"ci_low": 7, "ci_high": 11},
            "perf.p95_tat": {"ci_low": 5, "ci_high": 9},
        },
    }
    # a.throughput ci [8,12], b.throughput [7,11] -> a.ci_low 8 < b.ci_high 11, so a not clearly >= b on throughput
    assert _pareto_dominates_robust(a, b, objectives, row_to_ci) is False
    assert _pareto_dominates_robust(b, a, objectives, row_to_ci) is False


def test_compute_nondominated_per_scale_robust_single_row_per_cell() -> None:
    """With one row per cell, robust front equals point front."""
    rows = [
        {
            "method_id": "m1",
            "scale_id": "s1",
            "injection_id": "none",
            "perf.throughput": 5,
            "perf.p95_tat": 20,
            "safety.violations_total": 0,
            "sec.attack_success_rate": 0,
        },
        {
            "method_id": "m2",
            "scale_id": "s1",
            "injection_id": "none",
            "perf.throughput": 10,
            "perf.p95_tat": 15,
            "safety.violations_total": 0,
            "sec.attack_success_rate": 0,
        },
    ]
    point_front = compute_nondominated_per_scale(rows, DEFAULT_OBJECTIVES)
    robust_front = compute_nondominated_per_scale_robust(rows, DEFAULT_OBJECTIVES, seed=42)
    assert set(point_front.keys()) == set(robust_front.keys())
    for scale_id in point_front:
        assert len(point_front[scale_id]) == len(robust_front[scale_id])
        assert set(_row_key(r) for r in point_front[scale_id]) == set(_row_key(r) for r in robust_front[scale_id])


def test_compute_nondominated_per_scale_robust_structure() -> None:
    """Robust returns dict scale_id -> list of rows."""
    rows = [
        {
            "method_id": "m1",
            "scale_id": "s1",
            "injection_id": "i1",
            "perf.throughput": 1,
            "perf.p95_tat": 10,
            "safety.violations_total": 0,
            "sec.attack_success_rate": 0,
        },
    ]
    out = compute_nondominated_per_scale_robust(rows, DEFAULT_OBJECTIVES, seed=42)
    assert out == {"s1": rows}
