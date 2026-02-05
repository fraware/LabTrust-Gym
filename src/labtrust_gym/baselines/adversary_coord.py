"""
Deterministic coordination red-team adversary library for TaskH.

Strategies: collusion, slow-roll poisoning, identity rotation, replay attempts.
Clear definitions of success, detection, and containment for official runs.
Mixed honest/malicious population is supported via injection intensity and
per-agent targeting in the risk injectors.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class RedTeamStrategy(str, Enum):
    """Named strategies for coordination red-team evaluation."""

    COLLUSION = "collusion"
    SLOW_ROLL_POISONING = "slow_roll_poisoning"
    IDENTITY_ROTATION = "identity_rotation"
    REPLAY_ATTEMPTS = "replay_attempts"
    STEALTHY_POISONING = "stealthy_poisoning"
    DELAYED_TRIGGER = "delayed_trigger"


# Strategy -> injection_id for risk_injections. Deterministic runs use these IDs.
STRATEGY_TO_INJECTION_ID: Dict[RedTeamStrategy, str] = {
    RedTeamStrategy.COLLUSION: "INJ-COLLUSION-001",
    RedTeamStrategy.SLOW_ROLL_POISONING: "INJ-SLOW-POISON-001",
    RedTeamStrategy.IDENTITY_ROTATION: "INJ-ID-SPOOF-001",
    RedTeamStrategy.REPLAY_ATTEMPTS: "INJ-REPLAY-001",
    RedTeamStrategy.STEALTHY_POISONING: "INJ-COMMS-POISON-001",
    RedTeamStrategy.DELAYED_TRIGGER: "INJ-MEMORY-POISON-001",
}


@dataclass
class SuccessDetectionContainment:
    """Canonical definitions for red-team evaluation."""

    success_definition: str
    detection_definition: str
    containment_definition: str


# Per-strategy definitions (consistent with risk_injectors and metrics)
RED_TEAM_DEFINITIONS: Dict[RedTeamStrategy, SuccessDetectionContainment] = {
    RedTeamStrategy.COLLUSION: SuccessDetectionContainment(
        success_definition="Colluding bid accepted and affects allocation (starved/unfair).",
        detection_definition="Bid anomaly or signature/RBAC flags spoofed or biased bid.",
        containment_definition="Auction rejects/throttles; no allocation from colluding bid.",
    ),
    RedTeamStrategy.SLOW_ROLL_POISONING: SuccessDetectionContainment(
        success_definition="Poisoned state consumed after delay; wrong decision or release.",
        detection_definition="Integrity/consistency check detects corrupted state first.",
        containment_definition="Rollback or quarantine; no RELEASE_RESULT from poisoned path.",
    ),
    RedTeamStrategy.IDENTITY_ROTATION: SuccessDetectionContainment(
        success_definition="Action accepted under spoofed agent_id or key_id.",
        detection_definition="Signature/RBAC attributes action to wrong identity.",
        containment_definition="BLOCKED: SIG_INVALID, SIG_ROLE_MISMATCH, or RBAC_ACTION_DENY.",
    ),
    RedTeamStrategy.REPLAY_ATTEMPTS: SuccessDetectionContainment(
        success_definition="Replayed message or action accepted as fresh.",
        detection_definition="Replay detection (nonce/sequence/bus) flags duplicate.",
        containment_definition="Rejected; strict signatures + bus replay protection block.",
    ),
    RedTeamStrategy.STEALTHY_POISONING: SuccessDetectionContainment(
        success_definition="Poisoned obs/message influences decision; no immediate violation.",
        detection_definition="Anomaly/checksum detects poisoned comms/obs before critical.",
        containment_definition="Throttle or block; no critical action from poisoned view.",
    ),
    RedTeamStrategy.DELAYED_TRIGGER: SuccessDetectionContainment(
        success_definition="State corruption leads to wrong release/handoff after delay.",
        detection_definition="Memory/state integrity check detects corruption before use.",
        containment_definition="SEC_INJ_* triggered; no release from corrupted state.",
    ),
}


def get_injection_id_for_strategy(strategy: RedTeamStrategy) -> str:
    """Return the injection_id used for this strategy in official runs."""
    return STRATEGY_TO_INJECTION_ID.get(strategy, "")


def get_definitions_for_strategy(strategy: RedTeamStrategy) -> Optional[SuccessDetectionContainment]:
    """Return success/detection/containment definitions for the strategy."""
    return RED_TEAM_DEFINITIONS.get(strategy)


def all_strategies() -> List[RedTeamStrategy]:
    """Return all red-team strategies in stable order."""
    return [
        RedTeamStrategy.COLLUSION,
        RedTeamStrategy.SLOW_ROLL_POISONING,
        RedTeamStrategy.IDENTITY_ROTATION,
        RedTeamStrategy.REPLAY_ATTEMPTS,
        RedTeamStrategy.STEALTHY_POISONING,
        RedTeamStrategy.DELAYED_TRIGGER,
    ]


def strategy_for_injection_id(injection_id: str) -> Optional[RedTeamStrategy]:
    """Return the strategy that uses this injection_id, or None."""
    for s, iid in STRATEGY_TO_INJECTION_ID.items():
        if iid == injection_id:
            return s
    return None


@dataclass
class RedTeamScheduleEntry:
    """Single deterministic action: at step_index apply injection_id with intensity."""

    step_index: int
    injection_id: str
    intensity: float = 0.2


def deterministic_schedule_for_strategy(
    strategy: RedTeamStrategy,
    horizon_steps: int = 200,
    seed: int = 0,
) -> List[RedTeamScheduleEntry]:
    """
    Deterministic schedule (step, injection_id, intensity) for strategy.
    Same seed => same schedule (official runs).
    """
    import random

    rng = random.Random(seed)
    injection_id = get_injection_id_for_strategy(strategy)
    if not injection_id:
        return []
    frac = 0.1 + 0.3 * (rng.random() if horizon_steps > 0 else 0)
    step = max(1, min(int(horizon_steps * frac), horizon_steps - 1))
    intensity = 0.2 + 0.3 * (rng.random() if horizon_steps > 0 else 0)
    intensity = max(0.1, min(0.5, intensity))
    return [RedTeamScheduleEntry(step_index=step, injection_id=injection_id, intensity=intensity)]


def evaluate_episode_outcome(
    attack_success: bool,
    first_detection_step: Optional[int],
    first_containment_step: Optional[int],
    first_application_step: Optional[int],
) -> Dict[str, Any]:
    """
    Evaluate episode: success, detected, contained, stealth_success (success w/o detection).
    """
    detected = first_detection_step is not None
    contained = first_containment_step is not None
    stealth_success = attack_success and not detected
    return {
        "success": attack_success,
        "detected": detected,
        "contained": contained,
        "stealth_success": stealth_success,
        "first_detection_step": first_detection_step,
        "first_containment_step": first_containment_step,
        "first_application_step": first_application_step,
    }
