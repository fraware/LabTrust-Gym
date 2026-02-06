"""
Clock skew injection INJ-CLOCK-SKEW-001: same seed => same skew/offset per agent.

Reproducibility: get_clock_config(agent_ids) is deterministic given reset(seed).
"""

from __future__ import annotations

from labtrust_gym.security.risk_injections import make_injector


def test_clock_skew_same_seed_same_config() -> None:
    """Same seed and agent_ids => identical (skew_ppm, offset_ms) from get_clock_config."""
    agent_ids = ["runner_0", "runner_1", "ops_0"]
    inj = make_injector("INJ-CLOCK-SKEW-001", intensity=0.3, seed_offset=0)
    inj.reset(42, None)
    skew_a, offset_a = inj.get_clock_config(agent_ids)
    inj.reset(42, None)
    skew_b, offset_b = inj.get_clock_config(agent_ids)
    assert skew_a == skew_b
    assert offset_a == offset_b
    assert set(skew_a) == set(agent_ids)
    assert set(offset_a) == set(agent_ids)


def test_clock_skew_different_seed_different_config() -> None:
    """Different seeds => different skew/offset (with high probability)."""
    agent_ids = ["runner_0", "ops_0"]
    inj = make_injector("INJ-CLOCK-SKEW-001", intensity=0.5, seed_offset=0)
    inj.reset(1, None)
    skew_1, offset_1 = inj.get_clock_config(agent_ids)
    inj.reset(2, None)
    skew_2, offset_2 = inj.get_clock_config(agent_ids)
    assert skew_1 != skew_2 or offset_1 != offset_2


def test_clock_skew_values_in_reasonable_range() -> None:
    """Skew and offset are bounded by intensity-scaled ranges."""
    agent_ids = ["runner_0"]
    inj = make_injector("INJ-CLOCK-SKEW-001", intensity=0.2, seed_offset=0)
    inj.reset(123, None)
    skew, offset = inj.get_clock_config(agent_ids)
    # intensity 0.2 => skew_ppm_range 70, offset_ms_range 35
    assert abs(skew["runner_0"]) <= 100.0
    assert abs(offset["runner_0"]) <= 60.0
