"""
R-FLOW-001 (Action inefficiency) and R-FLOW-002 (Action progress).

Evidence that flow-related metrics are computed and that zero-progress
episodes are measurable (throughput=0 when no RELEASE_RESULT).
"""

from __future__ import annotations

from labtrust_gym.benchmarks.metrics import compute_episode_metrics


def test_flow_inefficiency_metrics_computed() -> None:
    """R-FLOW-001/SEC-FLOW-INEF-001: Episode metrics include steps and perf (inefficiency)."""
    # Short episode: 5 steps, one release at step 2
    step_results_per_step = [
        [{"emits": [], "violations": [], "status": "OK"}],
        [{"emits": [], "violations": [], "status": "OK"}],
        [{"emits": ["RELEASE_RESULT"], "violations": [], "status": "OK"}],
        [{"emits": [], "violations": [], "status": "OK"}],
        [{"emits": [], "violations": [], "status": "OK"}],
    ]
    t_s_per_step = [10, 20, 30, 40, 50]
    metrics = compute_episode_metrics(
        step_results_per_step,
        t_s_per_step=t_s_per_step,
    )
    assert "steps" in metrics
    assert metrics["steps"] == 5
    assert metrics.get("throughput") == 1
    assert "p50_turnaround_s" in metrics or "p95_turnaround_s" in metrics
    assert metrics["steps"] <= 100


def test_flow_progress_no_release_zero_throughput() -> None:
    """R-FLOW-002/SEC-FLOW-PROGRESS-001: No RELEASE_RESULT -> throughput 0 (progress risk)."""
    step_results_per_step = [
        [{"emits": [], "violations": [], "status": "OK"}],
        [{"emits": [], "violations": [], "status": "BLOCKED", "blocked_reason_code": "RC_DEVICE_BUSY"}],
        [{"emits": [], "violations": [], "status": "OK"}],
    ]
    metrics = compute_episode_metrics(step_results_per_step)
    assert metrics["throughput"] == 0
    assert metrics["steps"] == 3


def test_compute_episode_metrics_on_time_rate_and_critical_compliance() -> None:
    """compute_episode_metrics produces on_time_rate when sla_turnaround_s and releases exist; critical_communication_compliance_rate when notify/ack present."""
    # Two releases (no accept_ts so TAT uses last_ts per release); sla above last_ts -> all on time
    step_results_per_step = [
        [{"emits": [], "violations": [], "status": "OK"}],
        [{"emits": ["RELEASE_RESULT"], "violations": [], "status": "OK"}],
        [{"emits": [], "violations": [], "status": "OK"}],
        [{"emits": ["RELEASE_RESULT"], "violations": [], "status": "OK"}],
    ]
    t_s_per_step = [10, 20, 40, 60]
    metrics = compute_episode_metrics(
        step_results_per_step,
        t_s_per_step=t_s_per_step,
        sla_turnaround_s=70,
    )
    assert metrics["throughput"] == 2
    assert metrics["on_time_rate"] is not None
    # Without accept_ts, turnaround_s_list = [last_ts] * throughput = [60, 60]; 60 <= 70 -> on_time_rate 1.0
    assert metrics["on_time_rate"] == 1.0

    # Critical: 2 notifies, 1 ack -> compliance 0.5
    step_results_critical = [
        [{"emits": ["NOTIFY_CRITICAL_RESULT"], "violations": [], "status": "OK"}],
        [{"emits": ["ACK_CRITICAL_RESULT"], "violations": [], "status": "OK"}],
        [{"emits": ["NOTIFY_CRITICAL_RESULT"], "violations": [], "status": "OK"}],
    ]
    metrics_crit = compute_episode_metrics(step_results_critical)
    assert metrics_crit["critical_communication_compliance_rate"] is not None
    assert metrics_crit["critical_communication_compliance_rate"] == 0.5
