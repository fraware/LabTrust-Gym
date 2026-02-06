"""
Coordination monitor: detects when agents act on views older than max_staleness_ms
for critical actions (START_RUN, OPEN_DOOR restricted). Emits COORD_STALE_DECISION
with reason_code COORD_STALE_VIEW. Deterministic.
"""

from __future__ import annotations

from typing import Any

REASON_COORD_STALE_VIEW = "COORD_STALE_VIEW"
EMIT_COORD_STALE_DECISION = "COORD_STALE_DECISION"
DEFAULT_MAX_STALENESS_MS = 500.0
DEFAULT_DT_MS = 10.0


def _is_critical_action(action_dict: dict[str, Any]) -> bool:
    """True if action is START_RUN or OPEN_DOOR (restricted door / critical)."""
    atype = (action_dict or {}).get("action_type") or ""
    if atype == "START_RUN":
        return True
    if atype == "OPEN_DOOR":
        args = (action_dict or {}).get("args") or {}
        if args.get("door_id", "").upper().find("RESTRICTED") >= 0:
            return True
        return True
    return False


def check_staleness(
    actions: dict[str, dict[str, Any]],
    view_snapshots: dict[str, dict[str, Any]],
    decision_step: int,
    dt_ms: float = DEFAULT_DT_MS,
    max_staleness_ms: float = DEFAULT_MAX_STALENESS_MS,
) -> tuple[int, list[dict[str, Any]], list[float]]:
    """
    For each agent with a critical action, check if view is stale.
    Returns (stale_count, emit_payloads, view_ages_ms_per_agent).
    view_ages_ms: one value per agent that had a snapshot (for mean/p95 metrics).
    """
    stale_count = 0
    emits: list[dict[str, Any]] = []
    view_ages_ms: list[float] = []

    for agent_id, action_dict in actions.items():
        snap = view_snapshots.get(agent_id) or {}
        last_processing_step = snap.get("last_processing_step")
        # Use explicit None check: step 0 is a valid processing step
        if last_processing_step is None:
            age_ms = 0.0
        else:
            age_ms = max(0.0, (decision_step - last_processing_step) * dt_ms)
        if last_processing_step is not None:
            view_ages_ms.append(age_ms)

        if not _is_critical_action(action_dict):
            continue

        if age_ms > max_staleness_ms:
            stale_count += 1
            emits.append(
                {
                    "emit": EMIT_COORD_STALE_DECISION,
                    "agent_id": agent_id,
                    "reason_code": REASON_COORD_STALE_VIEW,
                    "view_age_ms": round(age_ms, 2),
                    "max_staleness_ms": max_staleness_ms,
                    "decision_step": decision_step,
                    "last_processing_step": last_processing_step,
                }
            )

    return stale_count, emits, view_ages_ms


def count_critical_actions(actions: dict[str, dict[str, Any]]) -> int:
    """Number of agents with a critical action this step."""
    return sum(1 for ad in (actions or {}).values() if _is_critical_action(ad))


def timing_metrics(
    total_critical_actions: int,
    stale_count: int,
    view_ages_ms: list[float],
) -> dict[str, Any]:
    """Build timing.* metrics for results."""
    stale_rate = stale_count / total_critical_actions if total_critical_actions > 0 else 0.0
    if not view_ages_ms:
        return {
            "stale_action_rate": round(stale_rate, 4),
            "mean_view_age_ms": 0.0,
            "p95_view_age_ms": 0.0,
        }
    sorted_ages = sorted(view_ages_ms)
    n = len(sorted_ages)
    mean_ms = sum(view_ages_ms) / n
    p95_ms = sorted_ages[min(int(0.95 * n), n - 1)] if n else 0.0
    return {
        "stale_action_rate": round(stale_rate, 4),
        "mean_view_age_ms": round(mean_ms, 2),
        "p95_view_age_ms": round(p95_ms, 2),
    }
