"""
Guardrails for coordinator LLM backends: circuit breaker and rate limiter.

Wraps proposal_backend, bid_backend, and repair_backend so that 429/timeouts
and repeated failures open the circuit and rate limits cap coordinator calls.
Uses the same env knobs as the agent path (LABTRUST_CIRCUIT_BREAKER_*,
LABTRUST_RATE_LIMIT_*) or optional LABTRUST_COORD_* overrides.
"""

from __future__ import annotations

import logging
from typing import Any

from labtrust_gym.baselines.llm.throttle import (
    CircuitBreaker,
    RateLimiter,
    throttle_config_from_env,
)


def coordinator_throttle_config_from_env() -> dict[str, Any]:
    """
    Read throttle config for coordinator path.
    Prefer LABTRUST_COORD_CIRCUIT_BREAKER_* and LABTRUST_COORD_RATE_LIMIT_*
    when set; else fall back to shared LABTRUST_CIRCUIT_BREAKER_* and
    LABTRUST_RATE_LIMIT_*.
    """
    import os

    logger = logging.getLogger(__name__)
    out = dict(throttle_config_from_env())
    try:
        t = os.environ.get("LABTRUST_COORD_CIRCUIT_BREAKER_THRESHOLD", "").strip()
        if t.isdigit():
            out["circuit_consecutive_threshold"] = int(t)
    except (ValueError, TypeError) as e:
        logger.debug("Invalid LABTRUST_COORD_CIRCUIT_BREAKER_THRESHOLD, using default: %s", e)
    try:
        c = os.environ.get("LABTRUST_COORD_CIRCUIT_BREAKER_COOLDOWN", "").strip()
        if c.isdigit():
            out["circuit_cooldown_calls"] = int(c)
    except (ValueError, TypeError) as e:
        logger.debug("Invalid LABTRUST_COORD_CIRCUIT_BREAKER_COOLDOWN, using default: %s", e)
    try:
        m = os.environ.get("LABTRUST_COORD_RATE_LIMIT_MAX_CALLS", "").strip()
        if m.isdigit():
            out["rate_max_calls"] = int(m)
    except (ValueError, TypeError) as e:
        logger.debug("Invalid LABTRUST_COORD_RATE_LIMIT_MAX_CALLS, using default: %s", e)
    try:
        w = os.environ.get("LABTRUST_COORD_RATE_LIMIT_WINDOW_SECONDS", "").strip()
        if w:
            out["rate_window_seconds"] = float(w)
    except (ValueError, TypeError) as e:
        logger.debug("Invalid LABTRUST_COORD_RATE_LIMIT_WINDOW_SECONDS, using default: %s", e)
    return out


def _agent_ids_from_digest(digest: dict[str, Any]) -> list[str]:
    """Extract agent_id list from state digest per_agent."""
    per_agent = digest.get("per_agent") or []
    if not isinstance(per_agent, list):
        return []
    return [str(p.get("agent_id", "")) for p in per_agent if isinstance(p, dict) and p.get("agent_id")]


def _noop_proposal_for_digest(
    digest: dict[str, Any],
    step_id: int,
    method_id: str,
    reason_code: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build valid NOOP coordination proposal and meta for guardrail fallback."""
    agent_ids = _agent_ids_from_digest(digest)
    if not agent_ids:
        agent_ids = ["unknown"]
    per_agent = [
        {
            "agent_id": aid,
            "action_type": "NOOP",
            "args": {},
            "reason_code": reason_code,
        }
        for aid in sorted(agent_ids)
    ]
    proposal = {
        "proposal_id": f"guardrail_fallback_{step_id}",
        "step_id": step_id,
        "method_id": method_id,
        "per_agent": per_agent,
        "comms": [],
        "meta": {
            "backend_id": "coordinator_guardrail",
            "reason_code": reason_code,
            "latency_ms": 0.0,
        },
    }
    meta = {
        "backend_id": "coordinator_guardrail",
        "reason_code": reason_code,
        "latency_ms": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
    }
    return proposal, meta


def _noop_bid_proposal_for_digest(
    digest: dict[str, Any],
    step_id: int,
    method_id: str,
    reason_code: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """NOOP bid proposal (empty market) and meta for guardrail fallback."""
    proposal, meta = _noop_proposal_for_digest(digest, step_id, method_id, reason_code)
    proposal["market"] = []
    return proposal, meta


class CoordinatorGuardrailProposalBackend:
    """
    Wraps a proposal backend with circuit breaker and rate limiter.
    On circuit open or rate limit returns NOOP proposal with reason code.
    On 429/timeout from inner backend records block and returns NOOP.
    """

    def __init__(self, inner: Any, config: dict[str, Any] | None = None) -> None:
        self._inner = inner
        cfg = config or coordinator_throttle_config_from_env()
        self._circuit = CircuitBreaker(
            consecutive_threshold=cfg.get("circuit_consecutive_threshold", 5),
            cooldown_calls=cfg.get("circuit_cooldown_calls", 10),
        )
        self._rate = RateLimiter(
            max_calls=cfg.get("rate_max_calls", 60),
            window_seconds=cfg.get("rate_window_seconds", 60.0),
        )

    def reset(self, seed: int | None = None) -> None:
        self._circuit.reset()
        self._rate.reset()
        if hasattr(self._inner, "reset") and callable(self._inner.reset):
            self._inner.reset(seed if seed is not None else 0)

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        allowed_actions: list[str],
        step_id: int,
        method_id: str,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if self._circuit.should_skip_llm():
            return _noop_proposal_for_digest(state_digest, step_id, method_id, "CIRCUIT_BREAKER_OPEN")
        if not self._rate.allow_call():
            return _noop_proposal_for_digest(state_digest, step_id, method_id, "RATE_LIMITED")
        try:
            out = self._inner.generate_proposal(state_digest, allowed_actions, step_id, method_id, **kwargs)
        except Exception as e:
            logging.getLogger(__name__).warning("Coordinator proposal generation failed, using fallback: %s", e)
            self._circuit.record_block()
            return _noop_proposal_for_digest(
                state_digest,
                step_id,
                method_id,
                "CIRCUIT_BREAKER_OPEN",
            )
        if isinstance(out, tuple):
            proposal, meta = out[0], out[1]
        else:
            proposal, meta = out, {}
        self._rate.record_call()
        self._circuit.record_success()
        return proposal, meta


class CoordinatorGuardrailBidBackend:
    """
    Wraps a bid backend with circuit breaker and rate limiter.
    On skip returns NOOP bid proposal (empty market) with reason code.
    """

    def __init__(self, inner: Any, config: dict[str, Any] | None = None) -> None:
        self._inner = inner
        cfg = config or coordinator_throttle_config_from_env()
        self._circuit = CircuitBreaker(
            consecutive_threshold=cfg.get("circuit_consecutive_threshold", 5),
            cooldown_calls=cfg.get("circuit_cooldown_calls", 10),
        )
        self._rate = RateLimiter(
            max_calls=cfg.get("rate_max_calls", 60),
            window_seconds=cfg.get("rate_window_seconds", 60.0),
        )

    def reset(self, seed: int | None = None) -> None:
        self._circuit.reset()
        self._rate.reset()
        if hasattr(self._inner, "reset") and callable(self._inner.reset):
            self._inner.reset(seed if seed is not None else 0)

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        step_id: int,
        method_id: str,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if self._circuit.should_skip_llm():
            return _noop_bid_proposal_for_digest(state_digest, step_id, method_id, "CIRCUIT_BREAKER_OPEN")
        if not self._rate.allow_call():
            return _noop_bid_proposal_for_digest(state_digest, step_id, method_id, "RATE_LIMITED")
        try:
            out = self._inner.generate_proposal(state_digest, step_id, method_id, **kwargs)
        except Exception as e:
            logging.getLogger(__name__).warning("Coordinator bid proposal generation failed, using fallback: %s", e)
            self._circuit.record_block()
            return _noop_bid_proposal_for_digest(
                state_digest,
                step_id,
                method_id,
                "CIRCUIT_BREAKER_OPEN",
            )
        if isinstance(out, tuple):
            proposal, meta = out[0], out[1]
        else:
            proposal, meta = out, {}
        self._rate.record_call()
        self._circuit.record_success()
        return proposal, meta


def _noop_repair_result(
    agent_ids: list[str],
    reason_code: str,
) -> tuple[list[tuple[str, str, dict[str, Any]]], dict[str, Any]]:
    """Safe fallback for repair: all NOOP and meta with reason_code."""
    per_agent = [(aid, "NOOP", {}) for aid in sorted(agent_ids)]
    meta = {
        "backend_id": "coordinator_guardrail",
        "reason_code": reason_code,
        "latency_ms": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
    }
    return per_agent, meta


class CoordinatorGuardrailRepairBackend:
    """
    Wraps a repair backend with circuit breaker and rate limiter.
    On skip or inner failure returns NOOP repair result with reason code.
    """

    def __init__(self, inner: Any, config: dict[str, Any] | None = None) -> None:
        self._inner = inner
        cfg = config or coordinator_throttle_config_from_env()
        self._circuit = CircuitBreaker(
            consecutive_threshold=cfg.get("circuit_consecutive_threshold", 5),
            cooldown_calls=cfg.get("circuit_cooldown_calls", 10),
        )
        self._rate = RateLimiter(
            max_calls=cfg.get("rate_max_calls", 60),
            window_seconds=cfg.get("rate_window_seconds", 60.0),
        )

    def reset(self, seed: int | None = None) -> None:
        self._circuit.reset()
        self._rate.reset()
        if hasattr(self._inner, "reset") and callable(self._inner.reset):
            self._inner.reset(seed if seed is not None else 0)

    def repair(
        self,
        repair_input: dict[str, Any],
        agent_ids: list[str],
    ) -> tuple[list[tuple[str, str, dict[str, Any]]], dict[str, Any]]:
        if self._circuit.should_skip_llm():
            return _noop_repair_result(agent_ids, "CIRCUIT_BREAKER_OPEN")
        if not self._rate.allow_call():
            return _noop_repair_result(agent_ids, "RATE_LIMITED")
        try:
            per_agent, meta = self._inner.repair(repair_input, agent_ids)
        except Exception as e:
            logging.getLogger(__name__).warning("Coordinator repair failed, using fallback: %s", e)
            self._circuit.record_block()
            return _noop_repair_result(agent_ids, "CIRCUIT_BREAKER_OPEN")
        self._rate.record_call()
        self._circuit.record_success()
        return per_agent, meta


def _safe_detector_fallback_for_guardrail() -> Any:
    """Return no-op detector output for guardrail fallback (avoids coupling to detector_advisor)."""
    from labtrust_gym.baselines.coordination.assurance.detector_advisor import (
        DetectorOutput,
        DetectResult,
        RecommendResult,
    )

    return DetectorOutput(
        detect=DetectResult(
            is_attack_suspected=False,
            suspected_risk_id="",
            suspect_agent_ids=[],
        ),
        recommend=RecommendResult(
            enforcement_action="none",
            scope="",
            rationale_short="",
        ),
    )


class CoordinatorGuardrailDetectorBackend:
    """
    Wraps a detector backend with circuit breaker and rate limiter.
    On circuit open or rate limit returns safe no-op DetectorOutput.
    On exception from inner backend records block and returns fallback.
    """

    def __init__(self, inner: Any, config: dict[str, Any] | None = None) -> None:
        self._inner = inner
        cfg = config or coordinator_throttle_config_from_env()
        self._circuit = CircuitBreaker(
            consecutive_threshold=cfg.get("circuit_consecutive_threshold", 5),
            cooldown_calls=cfg.get("circuit_cooldown_calls", 10),
        )
        self._rate = RateLimiter(
            max_calls=cfg.get("rate_max_calls", 60),
            window_seconds=cfg.get("rate_window_seconds", 60.0),
        )

    def reset(self, seed: int | None = None) -> None:
        self._circuit.reset()
        self._rate.reset()
        if hasattr(self._inner, "reset") and callable(self._inner.reset):
            self._inner.reset(seed if seed is not None else 0)

    def detect(
        self,
        step: int,
        event_summary: dict[str, Any],
        comms_stats: dict[str, Any] | None,
    ) -> Any:
        if self._circuit.should_skip_llm():
            return _safe_detector_fallback_for_guardrail()
        if not self._rate.allow_call():
            return _safe_detector_fallback_for_guardrail()
        try:
            out = self._inner.detect(step, event_summary, comms_stats)
        except Exception as e:
            logging.getLogger(__name__).warning("Coordinator detector failed, using fallback: %s", e)
            self._circuit.record_block()
            return _safe_detector_fallback_for_guardrail()
        self._rate.record_call()
        self._circuit.record_success()
        return out
