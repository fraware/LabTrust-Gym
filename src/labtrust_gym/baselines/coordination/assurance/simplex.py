"""
Simplex-like coordination-layer assurance: shield validates plan against hard
constraints; on reject, fallback controller (safe_wait + local greedy) is used.
Deterministic. Shield failures produce structured evidence (emit + reason_code + counters).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from labtrust_gym.baselines.coordination.decision_types import RouteDecision

# Reason codes (must exist in reason_code_registry)
REASON_SHIELD_COLLISION = "COORD_SHIELD_REJECT_COLLISION"
REASON_SHIELD_RESTRICTED = "COORD_SHIELD_REJECT_RESTRICTED"
REASON_SHIELD_RBAC = "COORD_SHIELD_REJECT_RBAC"
EMIT_COORD_SHIELD_DECISION = "COORD_SHIELD_DECISION"


@dataclass
class ShieldResult:
    """Result of validate_plan: ok, reasons, and counters for evidence."""

    ok: bool
    reasons: List[str] = field(default_factory=list)
    counters: Dict[str, int] = field(default_factory=dict)


def _get_zone_from_obs(obs: Dict[str, Any]) -> str:
    z = obs.get("zone_id")
    if z is not None:
        return str(z)
    return ""


def _args_dict(args_tuple: Tuple[Tuple[str, Any], ...]) -> Dict[str, Any]:
    return dict(args_tuple) if args_tuple else {}


def _restricted_zone_ids_from_policy(policy: Dict[str, Any]) -> Set[str]:
    """Zones that require token for entry (from zone_layout)."""
    out: Set[str] = set()
    layout = (
        (policy or {}).get("zone_layout")
        or (policy or {}).get("zone_layout_policy")
        or {}
    )
    for z in layout.get("zones") or []:
        if isinstance(z, dict) and z.get("restricted") and z.get("zone_id"):
            out.add(str(z["zone_id"]))
    return out


def _agent_has_restricted_token(obs: Dict[str, Any]) -> bool:
    token_active = obs.get("token_active")
    if not isinstance(token_active, dict):
        return False
    return bool(token_active.get("TOKEN_RESTRICTED_ENTRY"))


def _agent_role_allows_start_run(policy: Dict[str, Any], agent_id: str) -> bool:
    rbac = (policy or {}).get("rbac_policy") or {}
    agents_map = rbac.get("agents") or {}
    role_id = agents_map.get(agent_id) if isinstance(agents_map, dict) else None
    if not role_id:
        return True
    roles = rbac.get("roles") or {}
    role = roles.get(role_id) if isinstance(roles, dict) else None
    if not role or not isinstance(role, dict):
        return True
    actions = role.get("allowed_actions") or []
    return "START_RUN" in actions


def validate_plan(
    route: RouteDecision,
    context: Any,
) -> ShieldResult:
    """
    Validate route against hard constraints: no collision (INV-ROUTE-001),
    no restricted edge without token (INV-ROUTE-002), RBAC/allowed device/zone.
    Returns ShieldResult(ok, reasons, counters). Deterministic.
    """
    from labtrust_gym.baselines.coordination.routing.invariants import (
        check_inv_route_001,
        check_inv_route_002,
    )
    from labtrust_gym.baselines.coordination.routing.graph import build_routing_graph

    policy = getattr(context, "policy", None) or {}
    obs = getattr(context, "obs", None) or {}
    t = getattr(context, "t", 0)
    device_zone = getattr(context, "device_zone", None) or {}

    reasons: List[str] = []
    counters: Dict[str, int] = {
        "collision": 0,
        "restricted": 0,
        "rbac": 0,
    }

    # Build planned occupancy: (agent_id, time_step, zone_id) for t and t+1
    planned: List[Tuple[str, int, str]] = []
    planned_moves: List[Tuple[str, int, str, str]] = []
    agent_ids_seen: Set[str] = set()

    for agent_id, action_type, args_tuple in route.per_agent:
        agent_ids_seen.add(agent_id)
        o = obs.get(agent_id) or {}
        current_zone = _get_zone_from_obs(o)
        args = _args_dict(args_tuple)

        if action_type == "MOVE":
            to_zone = args.get("to_zone") or current_zone
            from_zone = args.get("from_zone") or current_zone
            planned.append((agent_id, t, current_zone))
            planned.append((agent_id, t + 1, to_zone))
            planned_moves.append((agent_id, t, from_zone, to_zone))
        else:
            planned.append((agent_id, t, current_zone))
            planned.append((agent_id, t + 1, current_zone))

    # Ensure every agent in context has at least (t, zone) and (t+1, zone)
    for agent_id in getattr(context, "agent_ids", []) or list(obs.keys()):
        if agent_id in agent_ids_seen:
            continue
        o = obs.get(agent_id) or {}
        current_zone = _get_zone_from_obs(o)
        planned.append((agent_id, t, current_zone))
        planned.append((agent_id, t + 1, current_zone))

    # INV-ROUTE-001: collision
    collision_violations = check_inv_route_001(planned)
    if collision_violations:
        reasons.extend(collision_violations)
        counters["collision"] = len(collision_violations)

    # INV-ROUTE-002: restricted edge without token
    restricted_edges: Set[Tuple[str, str]] = set()
    try:
        layout = policy.get("zone_layout") or policy.get("zone_layout_policy") or {}
        if layout:
            graph = build_routing_graph(layout)
            restricted_edges = graph.restricted_edges_set
    except Exception:
        pass
    agent_has_token = {
        aid: _agent_has_restricted_token(obs.get(aid) or {}) for aid in agent_ids_seen
    }
    restricted_violations = check_inv_route_002(
        planned_moves, restricted_edges, agent_has_token
    )
    if restricted_violations:
        reasons.extend(restricted_violations)
        counters["restricted"] = len(restricted_violations)

    # RBAC: START_RUN at device in restricted zone without token, or role disallows START_RUN
    restricted_zones = _restricted_zone_ids_from_policy(policy)
    for agent_id, action_type, args_tuple in route.per_agent:
        if action_type != "START_RUN":
            continue
        args = _args_dict(args_tuple)
        device_id = args.get("device_id")
        if not device_id:
            continue
        zone_id = device_zone.get(device_id, "")
        o = obs.get(agent_id) or {}
        if not _agent_role_allows_start_run(policy, agent_id):
            reasons.append(
                f"{REASON_SHIELD_RBAC}: {agent_id} START_RUN at {device_id} not allowed by RBAC"
            )
            counters["rbac"] += 1
        elif zone_id in restricted_zones and not _agent_has_restricted_token(o):
            reasons.append(
                f"{REASON_SHIELD_RBAC}: {agent_id} START_RUN in restricted zone {zone_id} without token"
            )
            counters["rbac"] += 1

    ok = len(reasons) == 0
    return ShieldResult(ok=ok, reasons=reasons, counters=counters)


def select_controller(
    advanced_route: RouteDecision,
    fallback_route: RouteDecision,
    shield_ok: bool,
) -> RouteDecision:
    """
    Select which route to use: advanced if shield accepted, else fallback.
    Deterministic.
    """
    return advanced_route if shield_ok else fallback_route


def build_shield_payload(
    accepted: bool,
    reasons: List[str],
    counters: Dict[str, int],
    step_idx: int,
) -> Dict[str, Any]:
    """Build structured payload for COORD_SHIELD_DECISION emit."""
    reason_codes: List[str] = []
    if counters.get("collision", 0) > 0:
        reason_codes.append(REASON_SHIELD_COLLISION)
    if counters.get("restricted", 0) > 0:
        reason_codes.append(REASON_SHIELD_RESTRICTED)
    if counters.get("rbac", 0) > 0:
        reason_codes.append(REASON_SHIELD_RBAC)
    return {
        "emit": EMIT_COORD_SHIELD_DECISION,
        "accepted": accepted,
        "step_idx": step_idx,
        "reasons": reasons[:50],
        "reason_codes": reason_codes,
        "counters": dict(counters),
    }


def _safe_fallback_route(context: Any) -> RouteDecision:
    """Fallback route: all NOOP (safe_wait). Deterministic."""
    agent_ids = getattr(context, "agent_ids", None) or []
    if not agent_ids and hasattr(context, "obs"):
        agent_ids = sorted((context.obs or {}).keys())
    per_agent = tuple((aid, "NOOP", ()) for aid in agent_ids)
    return RouteDecision(per_agent=per_agent, explain="simplex_fallback")


def wrap_with_simplex_shield(
    advanced_method: Any,
    fallback_router: Optional[Any] = None,
) -> Any:
    """
    Wrap a CoordinationMethod (advanced) with Simplex shield. When shield rejects
    the advanced plan, fallback route (safe_wait = all NOOP, or fallback_router)
    is used. Sets last_shield_emits on self for runner to append to step_results.
    Returns a CoordinationMethod that implements step(), propose_actions(), etc.
    """
    from labtrust_gym.baselines.coordination.compose import (
        _route_to_action_dict,
        _stable_hash,
    )
    from labtrust_gym.baselines.coordination.decision_types import CoordinationDecision
    from labtrust_gym.baselines.coordination.interface import (
        ACTION_NOOP,
        CoordinationMethod,
    )

    class SimplexShieldMethod(CoordinationMethod):
        def __init__(self) -> None:
            self._advanced = advanced_method
            self._fallback_router = fallback_router
            self._last_shield_emits: List[Dict[str, Any]] = []

        @property
        def method_id(self) -> str:
            return getattr(self._advanced, "method_id", "advanced") + "_shielded"

        def reset(
            self,
            seed: int,
            policy: Dict[str, Any],
            scale_config: Dict[str, Any],
        ) -> None:
            fn = getattr(self._advanced, "reset", None)
            if callable(fn):
                fn(seed, policy, scale_config)
            if self._fallback_router and hasattr(self._fallback_router, "reset"):
                self._fallback_router.reset(seed)

        def step(
            self,
            context: Any,
        ) -> Tuple[Dict[str, Dict[str, Any]], Optional[Any]]:
            actions, decision = self._advanced.step(context)
            if decision is None:
                self._last_shield_emits = []
                return actions, None
            route = decision.route
            fallback_route = _safe_fallback_route(context)
            if self._fallback_router is not None:
                try:
                    fallback_route = self._fallback_router.route(
                        context,
                        decision.allocation,
                        decision.schedule,
                    )
                except Exception:
                    pass
            result = validate_plan(route, context)
            selected = select_controller(route, fallback_route, result.ok)
            payload = build_shield_payload(
                result.ok,
                result.reasons,
                result.counters,
                getattr(context, "t", 0),
            )
            self._last_shield_emits = [
                {
                    "emits": [EMIT_COORD_SHIELD_DECISION],
                    "coord_shield_payload": payload,
                }
            ]
            actions_from_route: Dict[str, Dict[str, Any]] = {}
            agent_ids = getattr(context, "agent_ids", []) or list(
                (getattr(context, "obs", None) or {}).keys()
            )
            for aid in agent_ids:
                actions_from_route[aid] = {"action_index": ACTION_NOOP}
            for agent_id, action_type, args_tuple in selected.per_agent:
                actions_from_route[agent_id] = _route_to_action_dict(
                    agent_id, action_type, args_tuple
                )
            new_decision = CoordinationDecision(
                method_id=decision.method_id,
                step_idx=decision.step_idx,
                seed=decision.seed,
                state_hash=decision.state_hash,
                allocation_hash=decision.allocation_hash,
                schedule_hash=decision.schedule_hash,
                route_hash=_stable_hash(selected.per_agent),
                allocation=decision.allocation,
                schedule=decision.schedule,
                route=selected,
                explain_allocation=decision.explain_allocation,
                explain_schedule=decision.explain_schedule,
                explain_route=selected.explain,
            )
            return actions_from_route, new_decision

        @property
        def last_shield_emits(self) -> List[Dict[str, Any]]:
            return getattr(self, "_last_shield_emits", [])

        def get_route_metrics(self) -> Optional[Dict[str, Any]]:
            return getattr(self._advanced, "get_route_metrics", lambda: None)()

        def get_alloc_metrics(self) -> Optional[Dict[str, Any]]:
            return getattr(self._advanced, "get_alloc_metrics", lambda: None)()

        def get_hierarchy_metrics(self) -> Optional[Dict[str, Any]]:
            return getattr(self._advanced, "get_hierarchy_metrics", lambda: None)()

        def propose_actions(
            self,
            obs: Dict[str, Any],
            infos: Dict[str, Dict[str, Any]],
            t: int,
        ) -> Dict[str, Dict[str, Any]]:
            if hasattr(self._advanced, "propose_actions"):
                return self._advanced.propose_actions(obs, infos, t)
            import random
            from labtrust_gym.baselines.coordination.compose import build_kernel_context

            policy = getattr(self._advanced, "_policy", {})
            scale_config = getattr(self._advanced, "_scale_config", {})
            seed = getattr(self._advanced, "_seed", 0)
            context = build_kernel_context(obs, infos, t, policy, scale_config, seed)
            actions, _ = self.step(context)
            return actions

    return SimplexShieldMethod()
