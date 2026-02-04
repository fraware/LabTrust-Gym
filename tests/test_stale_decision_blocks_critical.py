"""
Stale decision detection: when an agent acts on a view older than max_staleness_ms
for a critical action (START_RUN, OPEN_DOOR restricted), COORD_STALE_DECISION is
emitted and timing metrics (stale_action_rate, mean_view_age_ms, p95_view_age_ms)
are recorded. Deterministic.
"""

from __future__ import annotations

import pytest

from labtrust_gym.coordination.coordination_monitor import (
    REASON_COORD_STALE_VIEW,
    EMIT_COORD_STALE_DECISION,
    check_staleness,
    count_critical_actions,
    timing_metrics,
    DEFAULT_MAX_STALENESS_MS,
)


def test_stale_critical_action_emits_coord_stale_decision() -> None:
    """Agent with START_RUN and view older than max_staleness_ms yields emit."""
    # decision_step=10, last_processing_step=0 => age = 10 * dt_ms
    dt_ms = 10000.0  # 10s per step
    max_ms = 500.0
    actions = {
        "runner_0": {"action_index": 5, "action_type": "START_RUN", "args": {}},
    }
    view_snapshots = {
        "runner_0": {"last_processing_step": 0, "last_event_t_event": 0},
    }
    stale_count, emits, view_ages_ms = check_staleness(
        actions,
        view_snapshots,
        decision_step=10,
        dt_ms=dt_ms,
        max_staleness_ms=max_ms,
    )
    assert stale_count == 1
    assert len(emits) == 1
    assert emits[0]["emit"] == EMIT_COORD_STALE_DECISION
    assert emits[0]["reason_code"] == REASON_COORD_STALE_VIEW
    assert emits[0]["agent_id"] == "runner_0"
    assert emits[0]["view_age_ms"] == 100000.0  # 10 steps * 10000 ms
    assert emits[0]["max_staleness_ms"] == max_ms
    assert view_ages_ms == [100000.0]


def test_fresh_view_no_stale_emit() -> None:
    """View updated at decision_step => no COORD_STALE_DECISION."""
    dt_ms = 10000.0
    actions = {
        "runner_0": {"action_index": 5, "action_type": "START_RUN"},
    }
    view_snapshots = {
        "runner_0": {"last_processing_step": 10},
    }
    stale_count, emits, _ = check_staleness(
        actions, view_snapshots, decision_step=10, dt_ms=dt_ms
    )
    assert stale_count == 0
    assert len(emits) == 0


def test_non_critical_action_never_stale_emit() -> None:
    """MOVE or NOOP does not trigger stale emit even if view is old."""
    actions = {
        "runner_0": {"action_index": 3, "action_type": "MOVE", "args": {}},
    }
    view_snapshots = {
        "runner_0": {"last_processing_step": 0},
    }
    stale_count, emits, _ = check_staleness(
        actions,
        view_snapshots,
        decision_step=10,
        dt_ms=10000.0,
        max_staleness_ms=100.0,
    )
    assert stale_count == 0
    assert len(emits) == 0


def test_timing_metrics_deterministic() -> None:
    """timing_metrics produces stable stale_action_rate, mean_view_age_ms, p95_view_age_ms."""
    m = timing_metrics(
        total_critical_actions=10,
        stale_count=2,
        view_ages_ms=[10.0, 20.0, 100.0, 200.0, 500.0],
    )
    assert m["stale_action_rate"] == 0.2
    assert m["mean_view_age_ms"] == 166.0
    assert m["p95_view_age_ms"] == 500.0
    m2 = timing_metrics(10, 2, [10.0, 20.0, 100.0, 200.0, 500.0])
    assert m == m2


def test_count_critical_actions() -> None:
    """count_critical_actions counts START_RUN and OPEN_DOOR (restricted)."""
    actions = {
        "a": {"action_type": "START_RUN"},
        "b": {"action_type": "MOVE"},
        "c": {"action_type": "OPEN_DOOR", "args": {"door_id": "RESTRICTED_1"}},
    }
    assert count_critical_actions(actions) == 2
