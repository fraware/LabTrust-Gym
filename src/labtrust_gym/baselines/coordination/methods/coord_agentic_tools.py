"""
Tool registry and execution for coordinator agentic loop.

Tools are callables (obs, infos, step_t, method_state) -> dict. No env step is
executed; tools only read state and return a small result for the coordinator.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Type for a single tool: (obs, infos, step_t, method_state) -> result dict
CoordinatorToolFn = Callable[[dict[str, Any], dict[str, Any], int, dict[str, Any]], dict[str, Any]]


def tool_query_queue_state(
    obs: dict[str, Any],
    infos: dict[str, Any],
    step_t: int,
    method_state: dict[str, Any],
) -> dict[str, Any]:
    """Return a compact queue state summary from obs for the coordinator."""
    out: dict[str, Any] = {"step": step_t, "agents": {}}
    for agent_id, o in obs.items():
        if not isinstance(o, dict):
            continue
        q = o.get("queue_has_head") or o.get("queue_by_device")
        out["agents"][agent_id] = {"queue_summary": str(q)[:200]}
    return out


def tool_get_detector_recommendation(
    obs: dict[str, Any],
    infos: dict[str, Any],
    step_t: int,
    method_state: dict[str, Any],
) -> dict[str, Any]:
    """
    Call detector backend when available (method_state["detector_backend"]); return
    probability, abstain, enforcement_action, scope, rationale. Optional counterfactual.
    When no detector in state, return safe default (abstain=True, probability=0).
    """
    backend = method_state.get("detector_backend") if isinstance(method_state, dict) else None
    if backend is None or not hasattr(backend, "detect"):
        return {
            "enforcement_action": "none",
            "rationale": "no_detector",
            "probability": 0.0,
            "abstain": True,
            "counterfactual": None,
        }
    event_summary = {
        "step": step_t,
        "agent_count": len(obs),
        "obs_snapshot": obs,
        "comms_stats": infos.get("comms_stats") if isinstance(infos, dict) else {},
    }
    comms_stats = event_summary.get("comms_stats")
    try:
        out = backend.detect(step_t, event_summary, comms_stats)
    except Exception:
        return {
            "enforcement_action": "none",
            "rationale": "detector_error",
            "probability": 0.0,
            "abstain": True,
            "counterfactual": None,
        }
    rec = out.recommend if hasattr(out, "recommend") else None
    detect = out.detect if hasattr(out, "detect") else None
    action = rec.enforcement_action if rec else "none"
    scope = getattr(rec, "scope", "") or ""
    rationale = getattr(rec, "rationale_short", "") or ""
    prob = getattr(detect, "probability", 0.0) if detect else 0.0
    abstain = getattr(detect, "abstain", True) if detect else True
    counterfactual = getattr(detect, "counterfactual", None) if detect else None
    return {
        "enforcement_action": action,
        "scope": scope,
        "rationale": rationale,
        "probability": float(prob),
        "abstain": bool(abstain),
        "counterfactual": counterfactual,
        "is_attack_suspected": getattr(detect, "is_attack_suspected", False) if detect else False,
    }


def tool_get_detector_recommendation_stub(
    obs: dict[str, Any],
    infos: dict[str, Any],
    step_t: int,
    method_state: dict[str, Any],
) -> dict[str, Any]:
    """Legacy stub name: delegates to tool_get_detector_recommendation."""
    return tool_get_detector_recommendation(obs, infos, step_t, method_state)


DEFAULT_COORD_TOOL_REGISTRY: dict[str, CoordinatorToolFn] = {
    "query_queue_state": tool_query_queue_state,
    "get_detector_recommendation": tool_get_detector_recommendation,
}


def run_tools(
    tool_calls: list[dict[str, Any]],
    obs: dict[str, Any],
    infos: dict[str, Any],
    step_t: int,
    method_state: dict[str, Any],
    registry: dict[str, CoordinatorToolFn] | None = None,
) -> list[dict[str, Any]]:
    """
    Execute tool calls and return list of results (one per call).
    Each tool_call: {"name": str, "args": dict}. Result: {"name", "result": dict}.
    """
    reg = registry or DEFAULT_COORD_TOOL_REGISTRY
    results: list[dict[str, Any]] = []
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        name = tc.get("name") or tc.get("tool")
        if name not in reg:
            results.append({"name": name, "result": {"error": "unknown_tool"}})
            continue
        _args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
        try:
            result = reg[name](obs, infos, step_t, method_state)
            results.append({"name": name, "result": result})
        except Exception as e:
            results.append({"name": name, "result": {"error": str(e)[:100]}})
    return results
