"""
Simplex-like coordination-layer assurance: shield validates plan against hard
constraints; on reject, fallback controller (safe_wait + local greedy) is used.
Deterministic. Shield failures produce structured evidence (emit + reason_code + counters).

Assurance evidence: COORD_SHIELD_DECISION emit includes assurance_evidence list with
claim_id (e.g. SC-SECURITY-ROUTE-001), control_id (CTRL-COORD-SIMPLEX), invariant_id
(INV-ROUTE-001, INV-ROUTE-002, INV-ROUTE-SWAP) for audit and safety-case traceability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from labtrust_gym.baselines.coordination.decision_types import RouteDecision
from labtrust_gym.baselines.coordination.routing.invariants import (
    INV_ROUTE_001,
    INV_ROUTE_002,
    INV_ROUTE_SWAP,
)

# Reason codes (must exist in reason_code_registry)
REASON_SHIELD_COLLISION = "COORD_SHIELD_REJECT_COLLISION"
REASON_SHIELD_RESTRICTED = "COORD_SHIELD_REJECT_RESTRICTED"
REASON_SHIELD_SWAP = "COORD_SHIELD_REJECT_SWAP"
REASON_SHIELD_RBAC = "COORD_SHIELD_REJECT_RBAC"
EMIT_COORD_SHIELD_DECISION = "COORD_SHIELD_DECISION"

# Safety-case traceability: claim_id / control_id / invariant_id for evidence.
# REASON_TO_EVIDENCE_MAP links each reject reason to (claim_id, control_id, invariant_id)
# for COORD_SHIELD_DECISION assurance_evidence; see docs/risk-and-security/output_controls.md.
SHIELD_CLAIM_ROUTE_SAFETY = "SC-SECURITY-ROUTE-001"
SHIELD_CLAIM_RBAC = "SC-SECURITY-RBAC-001"
SHIELD_CTRL_SIMPLEX = "CTRL-COORD-SIMPLEX"

REASON_TO_EVIDENCE_MAP = {
    REASON_SHIELD_COLLISION: (SHIELD_CLAIM_ROUTE_SAFETY, SHIELD_CTRL_SIMPLEX, INV_ROUTE_001),
    REASON_SHIELD_RESTRICTED: (SHIELD_CLAIM_ROUTE_SAFETY, SHIELD_CTRL_SIMPLEX, INV_ROUTE_002),
    REASON_SHIELD_SWAP: (SHIELD_CLAIM_ROUTE_SAFETY, SHIELD_CTRL_SIMPLEX, INV_ROUTE_SWAP),
    REASON_SHIELD_RBAC: (SHIELD_CLAIM_RBAC, SHIELD_CTRL_SIMPLEX, None),
}


@dataclass
class ShieldResult:
    """Result of validate_plan: ok, reasons, and counters for evidence."""

    ok: bool
    reasons: list[str] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)


def _get_zone_from_obs(obs: dict[str, Any]) -> str:
    z = obs.get("zone_id")
    if z is not None:
        return str(z)
    return ""


def _args_dict(args_tuple: tuple[tuple[str, Any], ...]) -> dict[str, Any]:
    return dict(args_tuple) if args_tuple else {}


def _restricted_zone_ids_from_policy(policy: dict[str, Any]) -> set[str]:
    """Zones that require token for entry (from zone_layout)."""
    out: set[str] = set()
    layout = (policy or {}).get("zone_layout") or (policy or {}).get("zone_layout_policy") or {}
    for z in layout.get("zones") or []:
        if isinstance(z, dict) and z.get("restricted") and z.get("zone_id"):
            out.add(str(z["zone_id"]))
    return out


def _agent_has_restricted_token(obs: dict[str, Any]) -> bool:
    token_active = obs.get("token_active")
    if not isinstance(token_active, dict):
        return False
    return bool(token_active.get("TOKEN_RESTRICTED_ENTRY"))


def _agent_role_allows_start_run(policy: dict[str, Any], agent_id: str) -> bool:
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
    no restricted edge without token (INV-ROUTE-002), swap (INV-ROUTE-SWAP),
    RBAC/allowed device/zone. Optional: no duplicate (agent, device, start_time)
    in schedule (when route includes START_RUN actions). device_zone and
    policy.zone_layout / zone_layout_policy must be passed correctly from
    compose/kernel. Returns ShieldResult(ok, reasons, counters). Deterministic.
    """
    from labtrust_gym.baselines.coordination.routing.graph import build_routing_graph
    from labtrust_gym.baselines.coordination.routing.invariants import (
        check_inv_route_001,
        check_inv_route_002,
        check_swap_collision,
    )

    policy = getattr(context, "policy", None) or {}
    obs = getattr(context, "obs", None) or {}
    t = getattr(context, "t", 0)
    device_zone = getattr(context, "device_zone", None) or {}

    reasons: list[str] = []
    counters: dict[str, int] = {
        "collision": 0,
        "restricted": 0,
        "swap": 0,
        "rbac": 0,
        "schedule_duplicate": 0,
    }

    # Build planned occupancy: (agent_id, time_step, zone_id) for t and t+1
    planned: list[tuple[str, int, str]] = []
    planned_moves: list[tuple[str, int, str, str]] = []
    agent_ids_seen: set[str] = set()

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
    restricted_edges: set[tuple[str, str]] = set()
    try:
        layout = policy.get("zone_layout") or policy.get("zone_layout_policy") or {}
        if layout:
            graph = build_routing_graph(layout)
            restricted_edges = graph.restricted_edges_set
    except Exception:
        pass
    agent_has_token = {aid: _agent_has_restricted_token(obs.get(aid) or {}) for aid in agent_ids_seen}
    restricted_violations = check_inv_route_002(planned_moves, restricted_edges, agent_has_token)
    if restricted_violations:
        reasons.extend(restricted_violations)
        counters["restricted"] = len(restricted_violations)

    # INV-ROUTE-SWAP: swap collision (A->B and B->A at same t)
    swap_violations = check_swap_collision(planned_moves)
    if swap_violations:
        reasons.extend(swap_violations)
        counters["swap"] = len(swap_violations)

    # RBAC: START_RUN at device in restricted zone without token, or role disallows START_RUN
    restricted_zones = _restricted_zone_ids_from_policy(policy)
    start_run_triples: list[tuple[str, str, int]] = []
    for agent_id, action_type, args_tuple in route.per_agent:
        if action_type != "START_RUN":
            continue
        args = _args_dict(args_tuple)
        device_id = args.get("device_id")
        if not device_id:
            continue
        start_run_triples.append((agent_id, str(device_id), t))
        zone_id = device_zone.get(device_id, "")
        o = obs.get(agent_id) or {}
        if not _agent_role_allows_start_run(policy, agent_id):
            reasons.append(f"{REASON_SHIELD_RBAC}: {agent_id} START_RUN at {device_id} not allowed by RBAC")
            counters["rbac"] += 1
        elif zone_id in restricted_zones and not _agent_has_restricted_token(o):
            reasons.append(f"{REASON_SHIELD_RBAC}: {agent_id} START_RUN in restricted zone {zone_id} without token")
            counters["rbac"] += 1

    # Optional: no duplicate (agent, device, start_time) in schedule
    if len(start_run_triples) != len(set(start_run_triples)):
        seen: set[tuple[str, str, int]] = set()
        for triple in start_run_triples:
            if triple in seen:
                reasons.append(
                    f"COORD_SHIELD_SCHEDULE_DUPLICATE: duplicate (agent, device, start_time) {triple}"
                )
                counters["schedule_duplicate"] += 1
            seen.add(triple)

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


def _build_assurance_evidence(
    reason_codes: list[str],
    step_idx: int,
    outcome: str,
) -> list[dict[str, Any]]:
    """Build assurance evidence list for safety-case traceability (claim_id, control_id, step, outcome, reason_code, invariant_id)."""
    evidence: list[dict[str, Any]] = []
    for code in reason_codes:
        claim_id, control_id, invariant_id = REASON_TO_EVIDENCE_MAP.get(
            code, (SHIELD_CLAIM_ROUTE_SAFETY, SHIELD_CTRL_SIMPLEX, None)
        )
        entry: dict[str, Any] = {
            "claim_id": claim_id,
            "control_id": control_id,
            "step": step_idx,
            "outcome": outcome,
            "reason_code": code,
        }
        if invariant_id is not None:
            entry["invariant_id"] = invariant_id
        evidence.append(entry)
    return evidence


def build_shield_payload(
    accepted: bool,
    reasons: list[str],
    counters: dict[str, int],
    step_idx: int,
) -> dict[str, Any]:
    """Build structured payload for COORD_SHIELD_DECISION emit. Includes assurance_evidence for audit/safety-case link."""
    reason_codes: list[str] = []
    if counters.get("collision", 0) > 0:
        reason_codes.append(REASON_SHIELD_COLLISION)
    if counters.get("restricted", 0) > 0:
        reason_codes.append(REASON_SHIELD_RESTRICTED)
    if counters.get("swap", 0) > 0:
        reason_codes.append(REASON_SHIELD_SWAP)
    if counters.get("rbac", 0) > 0:
        reason_codes.append(REASON_SHIELD_RBAC)
    outcome = "passed" if accepted else "blocked"
    assurance_evidence = _build_assurance_evidence(reason_codes, step_idx, outcome)
    if accepted and not reason_codes:
        assurance_evidence = [
            {
                "claim_id": SHIELD_CLAIM_ROUTE_SAFETY,
                "control_id": SHIELD_CTRL_SIMPLEX,
                "step": step_idx,
                "outcome": "passed",
                "reason_code": "",
            }
        ]
    return {
        "emit": EMIT_COORD_SHIELD_DECISION,
        "accepted": accepted,
        "shield_ok": accepted,
        "step_idx": step_idx,
        "reasons": reasons[:50],
        "reason_codes": reason_codes,
        "counters": dict(counters),
        "assurance_evidence": assurance_evidence,
    }


def _safe_fallback_route(context: Any) -> RouteDecision:
    """
    Fallback route: all NOOP (safe_wait). Deterministic.
    Semantics: safe_wait keeps every agent in place; no MOVE, so no collision,
    no restricted edge use, no swap. When fallback_router is provided to
    wrap_with_simplex_shield, local greedy routing may be used instead.
    """
    agent_ids = getattr(context, "agent_ids", None) or []
    if not agent_ids and hasattr(context, "obs"):
        agent_ids = sorted((context.obs or {}).keys())
    per_agent = tuple((aid, "NOOP", ()) for aid in agent_ids)
    return RouteDecision(per_agent=per_agent, explain="simplex_fallback")


def wrap_with_simplex_shield(
    advanced_method: Any,
    fallback_router: Any | None = None,
) -> Any:
    """
    Wrap a CoordinationMethod (advanced) with Simplex shield. When shield rejects
    the advanced plan, fallback route is used: safe_wait (all NOOP) or, if
    fallback_router is provided, local greedy routing. Fallback is always valid
    (no INV-ROUTE-001/002/SWAP violations; RBAC-respecting). Sets last_shield_emits
    on self for runner to append to step_results. Payload includes shield_ok
    for telemetry. Returns a CoordinationMethod that implements step(), propose_actions(), etc.
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
            self._last_shield_emits: list[dict[str, Any]] = []

        @property
        def method_id(self) -> str:
            return getattr(self._advanced, "method_id", "advanced") + "_shielded"

        def reset(
            self,
            seed: int,
            policy: dict[str, Any],
            scale_config: dict[str, Any],
        ) -> None:
            fn = getattr(self._advanced, "reset", None)
            if callable(fn):
                fn(seed, policy, scale_config)
            if self._fallback_router and hasattr(self._fallback_router, "reset"):
                self._fallback_router.reset(seed)

        def step(
            self,
            context: Any,
        ) -> tuple[dict[str, dict[str, Any]], Any | None]:
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
            actions_from_route: dict[str, dict[str, Any]] = {}
            agent_ids = getattr(context, "agent_ids", []) or list((getattr(context, "obs", None) or {}).keys())
            for aid in agent_ids:
                actions_from_route[aid] = {"action_index": ACTION_NOOP}
            for agent_id, action_type, args_tuple in selected.per_agent:
                actions_from_route[agent_id] = _route_to_action_dict(agent_id, action_type, args_tuple)
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
        def last_shield_emits(self) -> list[dict[str, Any]]:
            return getattr(self, "_last_shield_emits", [])

        def get_route_metrics(self) -> dict[str, Any] | None:
            return getattr(self._advanced, "get_route_metrics", lambda: None)()

        def get_alloc_metrics(self) -> dict[str, Any] | None:
            return getattr(self._advanced, "get_alloc_metrics", lambda: None)()

        def get_hierarchy_metrics(self) -> dict[str, Any] | None:
            return getattr(self._advanced, "get_hierarchy_metrics", lambda: None)()

        def propose_actions(
            self,
            obs: dict[str, Any],
            infos: dict[str, dict[str, Any]],
            t: int,
        ) -> dict[str, dict[str, Any]]:
            if hasattr(self._advanced, "propose_actions"):
                return self._advanced.propose_actions(obs, infos, t)  # type: ignore[no-any-return]
            from labtrust_gym.baselines.coordination.compose import build_kernel_context

            policy = getattr(self._advanced, "_policy", {})
            scale_config = getattr(self._advanced, "_scale_config", {})
            seed = getattr(self._advanced, "_seed", 0)
            context = build_kernel_context(obs, infos, t, policy, scale_config, seed)
            actions, _ = self.step(context)
            return cast(dict[str, dict[str, Any]], actions)  # type: ignore[redundant-cast]

    return SimplexShieldMethod()
