"""
Pareto evaluation determinism: same seed and summary_rows => same fronts and CIs.
"""

from __future__ import annotations

from labtrust_gym.benchmarks.pareto import (
    bootstrap_ci,
    build_pareto_artifact,
    compute_nondominated_per_scale,
    compute_per_method_ci,
)


def _two_cell_rows() -> list:
    return [
        {
            "method_id": "m1",
            "scale_id": "s1",
            "injection_id": "none",
            "perf.throughput": 10.0,
            "perf.p95_tat": 5.0,
            "safety.violations_total": 0,
            "sec.attack_success_rate": 0.0,
        },
        {
            "method_id": "m2",
            "scale_id": "s1",
            "injection_id": "none",
            "perf.throughput": 8.0,
            "perf.p95_tat": 4.0,
            "safety.violations_total": 1,
            "sec.attack_success_rate": 0.2,
        },
    ]


def test_nondominated_per_scale_deterministic() -> None:
    """Same rows => same nondominated sets (no randomness)."""
    rows = _two_cell_rows()
    a = compute_nondominated_per_scale(rows)
    b = compute_nondominated_per_scale(rows)
    assert list(a.keys()) == list(b.keys())
    for scale_id in a:
        assert len(a[scale_id]) == len(b[scale_id])
        method_ids_a = sorted(r.get("method_id") for r in a[scale_id])
        method_ids_b = sorted(r.get("method_id") for r in b[scale_id])
        assert method_ids_a == method_ids_b


def test_bootstrap_ci_same_seed_same_result() -> None:
    """Bootstrap CI is deterministic given seed."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    low1, mean1, high1 = bootstrap_ci(values, seed=42)
    low2, mean2, high2 = bootstrap_ci(values, seed=42)
    assert mean1 == mean2 == 3.0
    assert low1 == low2
    assert high1 == high2


def test_bootstrap_ci_different_seed_different_bounds() -> None:
    """Different seeds typically yield different bootstrap bounds (mean unchanged)."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0] * 4
    _, mean_a, _ = bootstrap_ci(values, seed=1)
    low_b, mean_b, high_b = bootstrap_ci(values, seed=2)
    assert mean_a == mean_b
    assert low_b <= mean_b <= high_b


def test_build_pareto_artifact_deterministic() -> None:
    """Same summary_rows and seed => same artifact (fronts + per_method_ci)."""
    rows = _two_cell_rows() + [
        {
            "method_id": "m1",
            "scale_id": "s1",
            "injection_id": "inj1",
            "perf.throughput": 9.0,
            "perf.p95_tat": 6.0,
            "safety.violations_total": 0,
            "sec.attack_success_rate": 0.1,
        },
    ]
    a = build_pareto_artifact(rows, seed=100)
    b = build_pareto_artifact(rows, seed=100)
    assert a["seed"] == b["seed"] == 100
    assert a["fronts_per_scale"].keys() == b["fronts_per_scale"].keys()
    for scale_id in a["fronts_per_scale"]:
        fa = a["fronts_per_scale"][scale_id]
        fb = b["fronts_per_scale"][scale_id]
        assert len(fa) == len(fb)
    assert a["per_method_ci"].keys() == b["per_method_ci"].keys()
    for method_id in a["per_method_ci"]:
        for key in a["per_method_ci"][method_id]:
            assert a["per_method_ci"][method_id][key] == b["per_method_ci"][method_id][key]


def test_compute_per_method_ci_deterministic() -> None:
    """Same rows and seed => same per-method CIs."""
    rows = _two_cell_rows()
    a = compute_per_method_ci(rows, seed=7)
    b = compute_per_method_ci(rows, seed=7)
    assert a.keys() == b.keys()
    for mid in a:
        assert a[mid].keys() == b[mid].keys()
        for metric in a[mid]:
            assert a[mid][metric] == b[mid][metric]
