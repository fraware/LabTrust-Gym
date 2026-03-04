"""Unit tests for rate uncertainty (Clopper-Pearson CI and worst-case failure rate)."""

from __future__ import annotations

from labtrust_gym.benchmarks.rate_uncertainty import (
    clopper_pearson_ci,
    worst_case_failure_rate_upper,
    worst_case_success_rate_upper,
)


class TestClopperPearsonCi:
    """Tests for clopper_pearson_ci."""

    def test_trials_zero_returns_zero_zero(self) -> None:
        assert clopper_pearson_ci(0, 0) == (0.0, 0.0)
        assert clopper_pearson_ci(5, 0) == (0.0, 0.0)

    def test_k_zero_lower_is_zero(self) -> None:
        low, high = clopper_pearson_ci(0, 10, 0.95)
        assert low == 0.0
        assert 0.0 < high < 1.0

    def test_k_equals_n_upper_is_one(self) -> None:
        low, high = clopper_pearson_ci(10, 10, 0.95)
        assert 0.0 < low < 1.0
        assert high == 1.0

    def test_lower_le_point_le_upper(self) -> None:
        for k, n in [(1, 10), (5, 10), (3, 7)]:
            low, high = clopper_pearson_ci(k, n, 0.95)
            p = k / n
            assert low <= p <= high, f"k={k} n={n}"

    def test_ci_bounded_zero_one(self) -> None:
        for k, n in [(0, 1), (1, 1), (0, 5), (3, 5), (5, 5)]:
            low, high = clopper_pearson_ci(k, n, 0.95)
            assert 0.0 <= low <= 1.0 and 0.0 <= high <= 1.0, f"k={k} n={n}"

    def test_k_clamped_to_valid_range(self) -> None:
        low_neg, high_neg = clopper_pearson_ci(-1, 10, 0.95)
        assert low_neg == 0.0 and high_neg < 1.0
        low_over, high_over = clopper_pearson_ci(20, 10, 0.95)
        assert low_over > 0.0 and high_over == 1.0

    def test_known_clopper_pearson_values(self) -> None:
        # Clopper-Pearson 95% for (5, 10): approx [0.19, 0.82]; Wilson fallback wider
        low, high = clopper_pearson_ci(5, 10, 0.95)
        assert 0.18 <= low <= 0.35
        assert 0.65 <= high <= 0.85

    def test_confidence_affects_width(self) -> None:
        low90, high90 = clopper_pearson_ci(5, 10, 0.90)
        low95, high95 = clopper_pearson_ci(5, 10, 0.95)
        assert high90 - low90 <= high95 - low95 + 1e-9  # 95% CI no narrower than 90%
        assert low95 <= low90 + 1e-9 and high90 <= high95 + 1e-9


class TestWorstCaseFailureRateUpper:
    """Tests for worst_case_failure_rate_upper."""

    def test_trials_zero_returns_one(self) -> None:
        assert worst_case_failure_rate_upper(0, 0.95) == 1.0

    def test_decreases_with_n(self) -> None:
        u10 = worst_case_failure_rate_upper(10, 0.95)
        u100 = worst_case_failure_rate_upper(100, 0.95)
        u1000 = worst_case_failure_rate_upper(1000, 0.95)
        assert u10 > u100 > u1000
        assert 0 < u1000 < 0.01

    def test_rule_of_three_approximation(self) -> None:
        # 95%: 1 - 0.95^(1/n) approx 3/n for moderate n
        for n in [10, 30, 100]:
            u = worst_case_failure_rate_upper(n, 0.95)
            rule3 = 3.0 / n
            assert abs(u - rule3) / max(u, rule3) < 0.5

    def test_confidence_affects_bound(self) -> None:
        u95 = worst_case_failure_rate_upper(20, 0.95)
        u99 = worst_case_failure_rate_upper(20, 0.99)
        assert u99 > u95


class TestWorstCaseSuccessRateUpper:
    """Tests for worst_case_success_rate_upper (0 successes observed)."""

    def test_trials_zero_returns_zero(self) -> None:
        assert worst_case_success_rate_upper(0, 0.95) == 0.0

    def test_decreases_with_n(self) -> None:
        u10 = worst_case_success_rate_upper(10, 0.95)
        u100 = worst_case_success_rate_upper(100, 0.95)
        assert u10 > u100
        assert 0 < u100 < 0.05

    def test_used_for_attack_success_upper_when_zero_successes(self) -> None:
        # When 0 attack successes in n episodes, upper bound for attack success rate
        u = worst_case_success_rate_upper(20, 0.95)
        assert 0.1 < u < 0.2


def test_summarize_v03_containment_success_rate_ci() -> None:
    """_aggregate_episodes_v03 adds containment_success_rate_ci_lower/upper when episodes have containment_success."""
    from labtrust_gym.benchmarks.summarize import _aggregate_episodes_v03

    episodes = [
        {"metrics": {"containment_success": True}},
        {"metrics": {"containment_success": False}},
        {"metrics": {"containment_success": True}},
    ]
    out = _aggregate_episodes_v03(episodes)
    assert "containment_success_rate_ci_lower" in out
    assert "containment_success_rate_ci_upper" in out
    assert out["containment_success_rate_ci_lower"] <= 2 / 3 <= out["containment_success_rate_ci_upper"]
