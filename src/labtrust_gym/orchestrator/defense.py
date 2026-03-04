"""
Operational kill switch and governance: on attack detection or invariant breach,
freeze zone / throttle / switch to safe baseline; require tokenized human override
to resume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DefenseState(Enum):
    """Orchestrator defense state. Normal -> Contained -> FallbackRequested -> Frozen (until override)."""

    NORMAL = "normal"
    CONTAINED = "contained"
    FALLBACK_REQUESTED = "fallback_requested"
    FROZEN = "frozen"


@dataclass
class DefenseController:
    """
    Observes step results for attack detection and invariant violations; transitions
    state to contained/fallback_requested/frozen. Resume from frozen only with valid
    human_override_token.
    """

    human_override_token: str | None = None
    """Expected token to clear FROZEN. Set from policy or env (e.g. LABTRUST_OVERRIDE_TOKEN)."""

    state: DefenseState = DefenseState.NORMAL
    """Current defense state."""

    transition_log: list[dict[str, Any]] = field(default_factory=list)
    """Log of (step, event, new_state) for audit."""

    # Emit types we treat as attack detection / containment (from risk_injections)
    EMIT_DETECTED = "SECURITY_INJECTION_DETECTED"
    EMIT_CONTAINED = "SECURITY_INJECTION_CONTAINED"
    EMIT_APPLIED = "SECURITY_INJECTION_APPLIED"

    def scan_step_results(self, step: int, step_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Scan step_results for SECURITY_INJECTION_*, BLOCKED, violations.
        Returns list of defense actions (freeze_zone, throttle, switch_to_baseline).
        Updates state and transition_log.
        """
        actions: list[dict[str, Any]] = []
        for r in step_results or []:
            emits = r.get("emits") or []
            if self.EMIT_DETECTED in emits or self.EMIT_CONTAINED in emits:
                if self.state == DefenseState.NORMAL:
                    self.state = DefenseState.CONTAINED
                    self.transition_log.append(
                        {
                            "step": step,
                            "event": "attack_detected_or_contained",
                            "emits": emits,
                            "new_state": self.state.value,
                        }
                    )
                    actions.append(
                        {
                            "type": "throttle",
                            "step": step,
                            "reason": "attack_detected_or_contained",
                        }
                    )
                if self.EMIT_CONTAINED in emits:
                    self.state = DefenseState.FALLBACK_REQUESTED
                    self.transition_log.append(
                        {
                            "step": step,
                            "event": "containment",
                            "new_state": self.state.value,
                        }
                    )
                    actions.append(
                        {
                            "type": "switch_to_baseline",
                            "step": step,
                            "reason": "containment",
                        }
                    )
            blocked = r.get("blocked_reason_code") or r.get("status") == "BLOCKED"
            if blocked and self.state == DefenseState.NORMAL:
                self.state = DefenseState.CONTAINED
                self.transition_log.append(
                    {
                        "step": step,
                        "event": "blocked",
                        "reason_code": r.get("blocked_reason_code"),
                        "new_state": self.state.value,
                    }
                )
            violations = r.get("violations") or []
            for v in violations:
                if v.get("status") == "VIOLATION":
                    if self.state == DefenseState.NORMAL:
                        self.state = DefenseState.CONTAINED
                        self.transition_log.append(
                            {
                                "step": step,
                                "event": "invariant_violation",
                                "invariant_id": v.get("invariant_id"),
                                "new_state": self.state.value,
                            }
                        )
                        actions.append(
                            {
                                "type": "freeze_zone",
                                "step": step,
                                "reason": "invariant_violation",
                                "invariant_id": v.get("invariant_id"),
                            }
                        )
                    self.state = DefenseState.FROZEN
                    self.transition_log.append(
                        {
                            "step": step,
                            "event": "frozen",
                            "reason": "invariant_violation",
                            "new_state": self.state.value,
                        }
                    )
                    actions.append(
                        {
                            "type": "kill_switch",
                            "step": step,
                            "reason": "invariant_violation",
                        }
                    )
                    break
        return actions

    def request_fallback(self) -> None:
        """Mark that fallback baseline has been requested (call after containment)."""
        if self.state in (DefenseState.CONTAINED, DefenseState.FALLBACK_REQUESTED):
            self.state = DefenseState.FALLBACK_REQUESTED

    def freeze(self, reason: str = "manual") -> None:
        """Set state to FROZEN (e.g. after kill_switch). Resume requires resume_risky_operations(token)."""
        self.state = DefenseState.FROZEN
        self.transition_log.append({"event": "freeze", "reason": reason, "new_state": self.state.value})

    def resume_risky_operations(self, override_token: str | None) -> bool:
        """
        If state is FROZEN and override_token matches human_override_token, set state to NORMAL and return True.
        Otherwise return False.
        """
        if self.state != DefenseState.FROZEN:
            return True
        if self.human_override_token is None:
            self.state = DefenseState.NORMAL
            self.transition_log.append(
                {"event": "resume", "reason": "no_token_required", "new_state": self.state.value}
            )
            return True
        if override_token != self.human_override_token:
            return False
        self.state = DefenseState.NORMAL
        self.transition_log.append({"event": "resume", "reason": "token_accepted", "new_state": self.state.value})
        return True

    def reset(self) -> None:
        """Reset state to NORMAL and clear transition_log (e.g. new episode)."""
        self.state = DefenseState.NORMAL
        self.transition_log.clear()
