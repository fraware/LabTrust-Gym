from __future__ import annotations

import math

import numpy as np
import pytest

from labtrust_gym.research.delayed_invalidation.bo_policy import (
    GpUcbPolicy,
    full_history_gp_ucb,
    observed_utility,
    sliding_window_gp_ucb,
    theory_guided_ucb_multiplier,
)
from labtrust_gym.research.delayed_invalidation.campaign import PolicyObservation


def _observations(n: int) -> list[PolicyObservation]:
    return [
        PolicyObservation(
            experiment_index=i + 1,
            x=(i + 0.5) / n,
            reported_ph=7.0 + 0.01 * i,
        )
        for i in range(n)
    ]


def test_observed_utility_is_zero_at_target_and_negative_elsewhere() -> None:
    assert observed_utility(7.40) == pytest.approx(0.0)
    assert observed_utility(7.20) == pytest.approx(-0.04)
    assert observed_utility(7.60) == pytest.approx(-0.04)


def test_ucb_schedule_matches_frozen_formula() -> None:
    assert theory_guided_ucb_multiplier(0) == pytest.approx(
        max(1.0, 1.7 * math.sqrt(2.0 * math.log(2.0)))
    )
    assert theory_guided_ucb_multiplier(10) > theory_guided_ucb_multiplier(0)
    with pytest.raises(ValueError):
        theory_guided_ucb_multiplier(-1)


def test_full_history_and_windows_are_frozen() -> None:
    full = full_history_gp_ucb()
    assert full.window_size is None
    for window in (20, 40, 80):
        assert sliding_window_gp_ucb(window).window_size == window
    with pytest.raises(ValueError):
        sliding_window_gp_ucb(30)


def test_window_selection_uses_most_recent_observations() -> None:
    policy = GpUcbPolicy(window_size=20)
    obs = _observations(50)
    selected = policy._training_observations(obs)
    assert len(selected) == 20
    assert selected[0].experiment_index == 31
    assert selected[-1].experiment_index == 50


def test_botorch_policy_if_research_environment_is_installed() -> None:
    pytest.importorskip("botorch")
    pytest.importorskip("gpytorch")
    pytest.importorskip("torch")

    policy = GpUcbPolicy(window_size=None, grid_points=101)
    rng = np.random.default_rng(12345)
    x = policy.choose_x(
        _observations(16),
        experiment_index=17,
        rng=rng,
    )
    assert 0.0 <= x <= 1.0
    assert x * 100 == pytest.approx(round(x * 100), abs=1e-9)
