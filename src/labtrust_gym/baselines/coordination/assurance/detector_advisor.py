"""
LLM detector throttle advisor: optional wrapper around any coordination method.

The detector (offline deterministic backend by default) reads a compact event stream
summary + comms stats and outputs detect + recommend. Only policy-allowed containment
actions are applied; invalid recommendations become NOOP with a reason code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

# Emit and reason code (must exist in emits_vocab and reason_code_registry)
EMIT_LLM_DETECTOR_DECISION = "LLM_DETECTOR_DECISION"
RC_DETECTOR_INVALID_RECOMMENDATION = "SEC_INJ_LLM_DETECTOR_INVALID"
RC_DETECTOR_CONTAINMENT_APPLIED = "SEC_INJ_LLM_DETECTOR_CONTAINMENT"

ALLOWED_ENFORCEMENT_ACTIONS = frozenset({"throttle", "freeze_zone", "kill_switch", "none"})


@dataclass
class DetectResult:
    """Detection result from the detector."""

    is_attack_suspected: bool
    suspected_risk_id: str = ""
    suspect_agent_ids: list[str] = field(default_factory=list)


@dataclass
class RecommendResult:
    """Enforcement recommendation from the detector."""

    enforcement_action: str  # throttle | freeze_zone | kill_switch | none
    scope: str | list[str] = ""
    rationale_short: str = ""


@dataclass
class DetectorOutput:
    """Full detector output: detect + recommend. Validated against schema."""

    detect: DetectResult
    recommend: RecommendResult


def _parse_scope(scope: str | list[str] | None, agent_ids: list[str]) -> list[str]:
    """Resolve scope to a list of agent ids. scope can be zone_id (string) or list of agent ids."""
    if scope is None:
        return []
    if isinstance(scope, list):
        return [str(a) for a in scope if a in agent_ids]
    # String: treat as single agent or zone; we have no zone->agents here, so use agent_ids for "all"
    s = str(scope).strip()
    if s in agent_ids:
        return [s]
    if s in ("*", "all", "all_agents"):
        return list(agent_ids)
    return []


def validate_recommendation(
    recommend: RecommendResult,
    allowed_actions: frozenset[str],
) -> tuple[bool, str | None]:
    """
    Validate detector recommendation against policy-allowed enforcement actions.
    Returns (valid, reason_code). reason_code set only when invalid.
    """
    action = (recommend.enforcement_action or "").strip().lower()
    if not action:
        return False, RC_DETECTOR_INVALID_RECOMMENDATION
    if action not in allowed_actions:
        return False, RC_DETECTOR_INVALID_RECOMMENDATION
    return True, None


class DetectorBackend(Protocol):
    """Protocol for detector backends: deterministic given (seed, step, event_summary)."""

    def detect(
        self,
        step: int,
        event_summary: dict[str, Any],
        comms_stats: dict[str, Any] | None,
    ) -> DetectorOutput:
        """Return detect + recommend from compact event summary and comms stats."""
        ...


def _queue_anomaly_score(obs: dict[str, Any]) -> float:
    """Heuristic: fraction of agents with non-zero queue_has_head sum (proxy for comms poison)."""
    total = 0
    anomalies = 0
    for _aid, o in obs.items():
        if not isinstance(o, dict):
            continue
        q = o.get("queue_has_head")
        if q is None:
            continue
        total += 1
        try:
            flat = getattr(q, "flat", q)
            arr = list(flat) if flat is not None else []
            if arr and sum(1 for x in arr if x) != len(arr) and sum(1 for x in arr if x) > 0:
                anomalies += 1
        except (TypeError, ValueError):
            pass
    return anomalies / total if total else 0.0


class DeterministicDetectorBackend:
    """
    Deterministic detector: flags attack within bounded latency when event summary
    suggests anomalies (e.g. queue_has_head inconsistency for INJ-COMMS-POISON-001).
    """

    def __init__(self, seed: int, latency_bound_steps: int = 5) -> None:
        self._seed = seed
        self._rng = __import__("random").Random(seed)
        self._latency_bound = max(1, latency_bound_steps)

    def detect(
        self,
        step: int,
        event_summary: dict[str, Any],
        comms_stats: dict[str, Any] | None,
    ) -> DetectorOutput:
        obs = event_summary.get("obs_snapshot") or event_summary.get("obs") or {}
        agent_ids = sorted(obs.keys()) if isinstance(obs, dict) else []
        anomaly = _queue_anomaly_score(obs)
        # After latency_bound steps, if anomaly score > 0, suspect attack and recommend throttle
        is_suspected = (
            step >= self._latency_bound
            and anomaly > 0
            and self._rng.random() < 0.95
        )
        suspect_ids: list[str] = []
        if is_suspected and agent_ids:
            # Pick one or two agents as suspects (deterministic from step)
            n = min(2, len(agent_ids))
            for i in range(n):
                idx = (step + self._seed + i) % len(agent_ids)
                suspect_ids.append(agent_ids[idx])
        action = "throttle" if is_suspected else "none"
        scope: list[str] = suspect_ids if suspect_ids else list(agent_ids)[:1]
        return DetectorOutput(
            detect=DetectResult(
                is_attack_suspected=is_suspected,
                suspected_risk_id="INJ-COMMS-POISON-001" if is_suspected else "",
                suspect_agent_ids=suspect_ids,
            ),
            recommend=RecommendResult(
                enforcement_action=action,
                scope=scope,
                rationale_short="queue_anomaly" if is_suspected else "",
            ),
        )


class _LLMDetectorThrottleAdvisor:
    """Wrapper that adds detector-based detection and policy-validated containment."""

    method_id = "llm_detector_throttle_advisor"

    def __init__(
        self,
        inner: Any,
        detector_backend: DetectorBackend,
        allowed_actions: frozenset[str],
    ) -> None:
        self._inner = inner
        self._backend = detector_backend
        self._allowed = allowed_actions
        self.last_detector_emits: list[dict[str, Any]] = []
        self._steps_with_detection: list[int] = []
        self._recommendations_total: int = 0
        self._invalid_recommendations: int = 0
        self._containment_applied_steps: list[int] = []
        self._episode_steps: int = 0

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self.last_detector_emits = []
        self._steps_with_detection = []
        self._recommendations_total = 0
        self._invalid_recommendations = 0
        self._containment_applied_steps = []
        self._episode_steps = 0
        if hasattr(self._inner, "reset"):
            self._inner.reset(seed, policy, scale_config)

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        self._episode_steps = t + 1
        actions_dict = self._inner.propose_actions(obs, infos, t)
        agent_ids = sorted(obs.keys()) if obs else []
        event_summary: dict[str, Any] = {
            "step": t,
            "agent_count": len(obs),
            "obs_snapshot": obs,
            "comms_stats": infos.get("comms_stats") if isinstance(infos, dict) else {},
        }
        comms_stats = event_summary.get("comms_stats")
        out = self._backend.detect(t, event_summary, comms_stats)
        self.last_detector_emits = []

        valid, reason_code = validate_recommendation(out.recommend, self._allowed)
        if out.recommend.enforcement_action and out.recommend.enforcement_action != "none":
            self._recommendations_total += 1
        if not valid and out.recommend.enforcement_action and out.recommend.enforcement_action != "none":
            self._invalid_recommendations += 1

        payload: dict[str, Any] = {
            "detect": {
                "is_attack_suspected": out.detect.is_attack_suspected,
                "suspected_risk_id": out.detect.suspected_risk_id or "",
                "suspect_agent_ids": list(out.detect.suspect_agent_ids),
            },
            "recommend": {
                "enforcement_action": out.recommend.enforcement_action,
                "scope": out.recommend.scope,
                "rationale_short": out.recommend.rationale_short or "",
            },
            "validation": {"valid": valid, "reason_code": reason_code},
        }
        self.last_detector_emits.append({
            "emits": [EMIT_LLM_DETECTOR_DECISION],
            "detector_payload": payload,
        })

        if out.detect.is_attack_suspected:
            self._steps_with_detection.append(t)

        applied = False
        if valid and out.recommend.enforcement_action in ("throttle", "kill_switch", "freeze_zone"):
            scope_agents = _parse_scope(
                out.recommend.scope,
                agent_ids or list(out.detect.suspect_agent_ids),
            )
            if not scope_agents and out.detect.suspect_agent_ids:
                scope_agents = [a for a in out.detect.suspect_agent_ids if a in (agent_ids or [])]
            if not scope_agents and agent_ids:
                scope_agents = agent_ids[:2]
            for aid in scope_agents:
                if aid in actions_dict:
                    actions_dict = dict(actions_dict)
                    actions_dict[aid] = dict(actions_dict[aid])
                    actions_dict[aid]["action_index"] = 0
                    applied = True
            if applied:
                self._containment_applied_steps.append(t)
                self.last_detector_emits.append({
                    "emits": [EMIT_LLM_DETECTOR_DECISION],
                    "status": "BLOCKED",
                    "blocked_reason_code": RC_DETECTOR_CONTAINMENT_APPLIED,
                })
        return actions_dict

    def on_step_result(self, step_results: list[dict[str, Any]]) -> None:
        if hasattr(self._inner, "on_step_result"):
            self._inner.on_step_result(step_results)

    def get_detector_metrics(self) -> dict[str, Any]:
        steps = max(1, self._episode_steps)
        rec_rate = self._recommendations_total / steps
        inv_rate = (
            self._invalid_recommendations / self._recommendations_total
            if self._recommendations_total else 0.0
        )
        return {
            "detector_suspected_at_steps": list(self._steps_with_detection),
            "detector_recommendation_rate": rec_rate,
            "detector_invalid_recommendation_rate": inv_rate,
            "detector_containment_applied_steps": list(self._containment_applied_steps),
        }


def wrap_with_detector_advisor(
    inner: Any,
    detector_backend: DetectorBackend,
    allowed_actions: frozenset[str] | None = None,
) -> Any:
    """
    Wrap a coordination method with the LLM detector throttle advisor.
    Inner method remains deterministic; detector recommends containment, validated
    against policy; valid throttle/kill_switch/freeze_zone override suspect agents' actions to NOOP.
    """
    allowed = allowed_actions or ALLOWED_ENFORCEMENT_ACTIONS
    return _LLMDetectorThrottleAdvisor(inner, detector_backend, allowed)
