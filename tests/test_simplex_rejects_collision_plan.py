"""
Simplex shield: plan with two agents moving to the same zone at the same step
is rejected with COORD_SHIELD_REJECT_COLLISION (INV-ROUTE-001).
"""

from __future__ import annotations

from labtrust_gym.baselines.coordination.assurance.simplex import (
    REASON_SHIELD_COLLISION,
    ShieldResult,
    validate_plan,
)
from labtrust_gym.baselines.coordination.decision_types import RouteDecision


class _MinimalContext:
    """Minimal context with obs, policy, t, agent_ids, device_zone."""

    def __init__(
        self,
        obs: dict,
        policy: dict,
        t: int = 0,
        agent_ids: list | None = None,
        device_zone: dict | None = None,
    ):
        self.obs = obs
        self.policy = policy or {}
        self.t = t
        self.agent_ids = agent_ids or sorted(obs.keys())
        self.device_zone = device_zone or {}


def test_shield_rejects_collision_two_agents_same_target() -> None:
    """Two agents MOVE to the same zone at same step => shield rejects with collision reason."""
    # Agent A at Z_A, Agent B at Z_B; both MOVE to Z_C => (t+1, Z_C) occupied by both
    route = RouteDecision(
        per_agent=(
            (
                "runner_0",
                "MOVE",
                (("from_zone", "Z_A"), ("to_zone", "Z_C")),
            ),
            (
                "runner_1",
                "MOVE",
                (("from_zone", "Z_B"), ("to_zone", "Z_C")),
            ),
        ),
        explain="collision_plan",
    )
    context = _MinimalContext(
        obs={
            "runner_0": {"zone_id": "Z_A"},
            "runner_1": {"zone_id": "Z_B"},
        },
        policy={},
        t=5,
    )
    result = validate_plan(route, context)
    assert isinstance(result, ShieldResult)
    assert result.ok is False
    assert result.counters.get("collision", 0) >= 1
    assert any(REASON_SHIELD_COLLISION in r or "INV-ROUTE-001" in r for r in result.reasons)


def test_shield_accepts_no_collision() -> None:
    """Two agents MOVE to different zones => no collision violation."""
    route = RouteDecision(
        per_agent=(
            ("runner_0", "MOVE", (("from_zone", "Z_A"), ("to_zone", "Z_B"))),
            ("runner_1", "MOVE", (("from_zone", "Z_C"), ("to_zone", "Z_D"))),
        ),
        explain="ok_plan",
    )
    context = _MinimalContext(
        obs={"runner_0": {"zone_id": "Z_A"}, "runner_1": {"zone_id": "Z_C"}},
        policy={},
        t=0,
    )
    result = validate_plan(route, context)
    assert result.ok is True
    assert result.counters.get("collision", 0) == 0
