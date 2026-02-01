"""
Per-episode metrics: throughput, turnaround, violations, blocked, trust proxies.

Aggregates from _benchmark_step_results collected during episode.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional

# Emits we track for metrics
EMIT_RELEASE_RESULT = "RELEASE_RESULT"
EMIT_ACCEPT_SPECIMEN = "ACCEPT_SPECIMEN"
EMIT_HOLD_SPECIMEN = "HOLD_SPECIMEN"
EMIT_MINT_TOKEN = "MINT_TOKEN"
EMIT_NOTIFY_CRITICAL = "NOTIFY_CRITICAL_RESULT"
EMIT_ACK_CRITICAL = "ACK_CRITICAL_RESULT"


# Security-related blocked reason codes (TaskF: insider containment)
SECURITY_REASON_CODES = frozenset({
    "RBAC_ACTION_DENY",
    "RBAC_ZONE_DENY",
    "RBAC_DEVICE_DENY",
    "SIG_MISSING",
    "SIG_INVALID",
    "SIG_KEY_REVOKED",
    "SIG_KEY_EXPIRED",
    "SIG_KEY_NOT_YET_VALID",
    "SIG_ROLE_MISMATCH",
})


def compute_episode_metrics(
    step_results_per_step: List[List[Dict[str, Any]]],
    t_s_per_step: Optional[List[int]] = None,
    sla_turnaround_s: Optional[int] = None,
    attack_start_step: Optional[int] = None,
    insider_attack_steps: Optional[List[int]] = None,
    timing_mode: str = "explicit",
    episode_time_s: Optional[int] = None,
    device_busy_s: Optional[Dict[str, int]] = None,
    queue_lengths_per_step: Optional[List[Dict[str, int]]] = None,
) -> Dict[str, Any]:
    """
    Compute per-episode metrics from list of step results (one list per step).

    step_results_per_step: list of lists; each inner list is the _benchmark_step_results
    for one env step (one result per agent).
    t_s_per_step: optional list of t_s for each step (default 10 * step_idx).
    sla_turnaround_s: optional SLA in seconds for on-time rate (accept->release).
    attack_start_step: optional (TaskD) first step index of adversarial action for detection_latency_s.
    insider_attack_steps: optional (TaskF) step indices of insider attack attempts for containment/forensic metrics.
    timing_mode: "explicit" | "simulated"; affects p95 meaning and enables device utilization / queue stats.
    episode_time_s: total episode time in seconds (simulated mode); for utilization = busy_s / episode_time_s.
    device_busy_s: per-device total busy seconds (simulated mode).
    queue_lengths_per_step: list of {device_id: queue_length} per step (simulated mode) for mean/max stats.
    """
    t_s_per_step = t_s_per_step or [
        10 * (i + 1) for i in range(len(step_results_per_step))
    ]
    throughput = 0
    violations_by_invariant: Dict[str, int] = defaultdict(int)
    blocked_by_reason: Dict[str, int] = defaultdict(int)
    tokens_consumed_count = 0
    tokens_minted_count = 0
    holds_count = 0
    accept_ts: Dict[str, int] = {}
    release_ts: Dict[str, int] = {}
    critical_notify_count = 0
    critical_ack_count = 0
    first_violation_step: Optional[int] = None
    first_enforcement_step: Optional[int] = None
    first_release_step: Optional[int] = None

    for step_idx, results in enumerate(step_results_per_step):
        t_s = (
            t_s_per_step[step_idx]
            if step_idx < len(t_s_per_step)
            else 10 * (step_idx + 1)
        )
        step_has_violation_or_blocked = False
        step_has_enforcement = False
        step_has_release = False
        for r in results:
            emits = r.get("emits") or []
            for e in emits:
                if e == EMIT_RELEASE_RESULT:
                    throughput += 1
                    step_has_release = True
                    release_ts[f"_r{throughput}"] = t_s
                elif e == EMIT_HOLD_SPECIMEN:
                    holds_count += 1
                elif e == EMIT_MINT_TOKEN:
                    tokens_minted_count += 1
                elif e == EMIT_NOTIFY_CRITICAL:
                    critical_notify_count += 1
                elif e == EMIT_ACK_CRITICAL:
                    critical_ack_count += 1
            for v in r.get("violations") or []:
                inv_id = v.get("invariant_id") or "unknown"
                violations_by_invariant[str(inv_id)] += 1
                if v.get("status") == "VIOLATION":
                    step_has_violation_or_blocked = True
            blocked_code = r.get("blocked_reason_code")
            if blocked_code:
                blocked_by_reason[str(blocked_code)] += 1
                step_has_violation_or_blocked = True
            for _ in r.get("token_consumed") or []:
                tokens_consumed_count += 1
            if r.get("enforcements"):
                step_has_enforcement = True
        if step_has_violation_or_blocked and first_violation_step is None:
            first_violation_step = step_idx
        if step_has_enforcement and first_enforcement_step is None:
            first_enforcement_step = step_idx
        if step_has_release and first_release_step is None:
            first_release_step = step_idx

    turnaround_s_list: List[int] = []
    if release_ts and accept_ts:
        for k, rel_ts in release_ts.items():
            acc_ts = accept_ts.get(k)
            if acc_ts is not None:
                turnaround_s_list.append(rel_ts - acc_ts)
    elif throughput > 0 and step_results_per_step:
        last_ts = t_s_per_step[-1] if t_s_per_step else 0
        turnaround_s_list = [last_ts] * throughput

    def _percentile(values: List[float], p: float) -> Optional[float]:
        if not values:
            return None
        sorted_v = sorted(values)
        k = (len(sorted_v) - 1) * p / 100.0
        lo = int(k)
        hi = min(lo + 1, len(sorted_v) - 1)
        return sorted_v[lo] + (k - lo) * (sorted_v[hi] - sorted_v[lo])

    turn_floats = [float(x) for x in turnaround_s_list]
    p50_turnaround_s = _percentile(turn_floats, 50)
    p95_turnaround_s = _percentile(turn_floats, 95)

    on_time_rate: Optional[float] = None
    if sla_turnaround_s is not None and turn_floats:
        on_time = sum(1 for t in turn_floats if t <= sla_turnaround_s)
        on_time_rate = on_time / len(turn_floats)

    critical_compliance: Optional[float] = None
    if critical_notify_count > 0:
        critical_compliance = (
            critical_ack_count / critical_notify_count
        )

    # Detection latency (TaskD): first violation ts - attack start ts
    detection_latency_s: Optional[float] = None
    if attack_start_step is not None and first_violation_step is not None:
        attack_ts = (
            t_s_per_step[attack_start_step]
            if attack_start_step < len(t_s_per_step)
            else None
        )
        violation_ts = (
            t_s_per_step[first_violation_step]
            if first_violation_step < len(t_s_per_step)
            else None
        )
        if attack_ts is not None and violation_ts is not None:
            detection_latency_s = float(violation_ts - attack_ts)

    # Containment: enforcement triggered before any release (or no release)
    containment_success: Optional[bool] = None
    if first_enforcement_step is not None:
        containment_success = (
            first_release_step is None
            or first_enforcement_step < first_release_step
        )
    elif first_release_step is not None:
        containment_success = False

    # Attribution proxy: audit log has agent_id + action chain per event
    attribution_confidence_proxy: Optional[float] = None
    if first_violation_step is not None:
        attribution_confidence_proxy = 1.0

    p95_note = (
        "Meaningful in simulated mode (device completion times)."
        if timing_mode == "simulated"
        else "Derived from step timestamps only (explicit mode)."
    )
    out: Dict[str, Any] = {
        "throughput": throughput,
        "p50_turnaround_s": p50_turnaround_s,
        "p95_turnaround_s": p95_turnaround_s,
        "p95_turnaround_s_note": p95_note,
        "timing_mode": timing_mode,
        "on_time_rate": on_time_rate,
        "violations_by_invariant_id": dict(violations_by_invariant),
        "blocked_by_reason_code": dict(blocked_by_reason),
        "critical_communication_compliance_rate": critical_compliance,
        "tokens_minted": tokens_minted_count,
        "tokens_consumed": tokens_consumed_count,
        "holds_count": holds_count,
        "steps": len(step_results_per_step),
    }

    # Simulated-mode-only: device utilization and queue length stats (always present in simulated, even if empty)
    if timing_mode == "simulated":
        device_utilization: Dict[str, float] = {}
        if episode_time_s and episode_time_s > 0 and device_busy_s:
            device_utilization = {
                did: (device_busy_s.get(did, 0) / episode_time_s)
                for did in device_busy_s
            }
        device_queue_length_mean: Dict[str, float] = {}
        device_queue_length_max: Dict[str, int] = {}
        if queue_lengths_per_step:
            all_devices: set = set()
            for step_q in queue_lengths_per_step:
                all_devices.update(step_q.keys())
            for did in sorted(all_devices):
                lengths = [step_q.get(did, 0) for step_q in queue_lengths_per_step]
                device_queue_length_mean[did] = statistics.mean(lengths)
                device_queue_length_max[did] = max(lengths) if lengths else 0
        out["device_utilization"] = device_utilization
        out["device_queue_length_mean"] = device_queue_length_mean
        out["device_queue_length_max"] = device_queue_length_max
    if detection_latency_s is not None:
        out["detection_latency_s"] = detection_latency_s
    if containment_success is not None:
        out["containment_success"] = containment_success
    if attribution_confidence_proxy is not None:
        out["attribution_confidence_proxy"] = attribution_confidence_proxy

    # TaskF: time_to_first_detected_security_violation, fraction_of_attacks_contained, forensic_quality_score
    if insider_attack_steps:
        first_security_block_step: Optional[int] = None
        for step_idx, results in enumerate(step_results_per_step):
            for r in results:
                if r.get("status") == "BLOCKED":
                    code = r.get("blocked_reason_code")
                    if code and str(code) in SECURITY_REASON_CODES:
                        if first_security_block_step is None:
                            first_security_block_step = step_idx
                        break
        time_to_first_detected_security_violation: Optional[float] = None
        if first_security_block_step is not None and first_security_block_step < len(t_s_per_step):
            time_to_first_detected_security_violation = float(t_s_per_step[first_security_block_step])

        contained_count = 0
        for step_idx in insider_attack_steps:
            if step_idx >= len(step_results_per_step):
                continue
            for r in step_results_per_step[step_idx]:
                if r.get("status") == "BLOCKED" and str(r.get("blocked_reason_code") or "") in SECURITY_REASON_CODES:
                    contained_count += 1
                    break
        fraction_of_attacks_contained: Optional[float] = None
        if insider_attack_steps:
            fraction_of_attacks_contained = contained_count / len(insider_attack_steps)

        forensic_quality_score: Optional[float] = None
        has_rbac = 0
        has_sig_when_needed = 0
        total = 0
        for results in step_results_per_step:
            for r in results:
                total += 1
                if r.get("rbac_decision") is not None:
                    has_rbac += 1
                if r.get("signature_verification") is not None or not (r.get("key_id") or r.get("signature")):
                    has_sig_when_needed += 1
        if total > 0:
            forensic_quality_score = (has_rbac / total + has_sig_when_needed / total) / 2.0

        if time_to_first_detected_security_violation is not None:
            out["time_to_first_detected_security_violation"] = time_to_first_detected_security_violation
        if fraction_of_attacks_contained is not None:
            out["fraction_of_attacks_contained"] = fraction_of_attacks_contained
        if forensic_quality_score is not None:
            out["forensic_quality_score"] = forensic_quality_score
    return out
