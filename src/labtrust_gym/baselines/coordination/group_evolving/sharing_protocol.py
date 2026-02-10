"""
Sharing protocol: build experience messages from buffer summaries and derive
routing weights (zone preference) for job routing / bid shading.
"""

from __future__ import annotations

from typing import Any


def build_experience_message(
    summaries: list[dict[str, Any]],
    step: int,
) -> dict[str, Any]:
    """
    Single experience message: aggregate zone-level reward/violations/blocks
    for downstream weight adjustment. Small payload.
    """
    zone_reward: dict[str, float] = {}
    zone_violations: dict[str, int] = {}
    zone_blocks: dict[str, int] = {}
    for s in summaries:
        z = s.get("z") or "_"
        zone_reward[z] = zone_reward.get(z, 0.0) + float(s.get("r") or 0.0)
        zone_violations[z] = zone_violations.get(z, 0) + int(s.get("v") or 0)
        if s.get("b"):
            zone_blocks[z] = zone_blocks.get(z, 0) + 1
    return {
        "step": step,
        "zone_reward": zone_reward,
        "zone_violations": zone_violations,
        "zone_blocks": zone_blocks,
    }


def summaries_to_routing_weights(
    messages: list[dict[str, Any]],
    default_weight: float = 1.0,
    violation_penalty: float = 0.2,
    block_penalty: float = 0.3,
) -> dict[str, float]:
    """
    Convert shared experience messages to zone_id -> weight (higher = prefer).
    Weights start at default_weight; subtract penalties for violations/blocks.
    """
    zone_score: dict[str, float] = {}
    for msg in messages:
        for z, v in (msg.get("zone_violations") or {}).items():
            zone_score[z] = zone_score.get(z, default_weight) - violation_penalty * v
        for z, b in (msg.get("zone_blocks") or {}).items():
            zone_score[z] = zone_score.get(z, default_weight) - block_penalty * b
        for z, r in (msg.get("zone_reward") or {}).items():
            if z not in zone_score:
                zone_score[z] = default_weight
            zone_score[z] = zone_score[z] + 0.1 * r
    return {z: max(0.01, w) for z, w in zone_score.items()} if zone_score else {}
