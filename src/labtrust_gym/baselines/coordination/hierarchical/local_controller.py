"""
Local controller: per-region kernel (allocation + EDF schedule + WHCA/Trivial route).
Operates on local view: agents and zones in this region only.
Deterministic; uses same kernel components as global composed methods.
"""

from __future__ import annotations

from typing import Any, cast

from labtrust_gym.baselines.coordination.coordination_kernel import KernelContext
from labtrust_gym.baselines.coordination.decision_types import (
    AllocationDecision,
    ScheduleDecision,
)
from labtrust_gym.baselines.coordination.kernel_components import (
    EDFScheduler,
    TrivialRouter,
)
from labtrust_gym.baselines.coordination.obs_utils import (
    get_zone_from_obs,
    log_frozen,
)

MacroAssignment = tuple[str, str, str, str, int, int]


class LocalController:
    """
    Runs allocation + EDF + routing for one region. Uses local obs (agents in region)
    and region-level work assignments from hub. Deterministic.
    """

    def __init__(self, use_whca: bool = False, whca_horizon: int = 10) -> None:
        self._use_whca = use_whca
        self._whca_horizon = whca_horizon
        self._scheduler = EDFScheduler()
        self._router = TrivialRouter()

    def step(
        self,
        region_id: str,
        region_agent_ids: list[str],
        region_zone_ids: list[str],
        region_device_ids: list[str],
        region_device_zone: dict[str, str],
        obs: dict[str, Any],
        region_assignments: list[MacroAssignment],
        policy: dict[str, Any],
        adjacency: Any,
        t: int,
        seed: int,
        rng: Any,
    ) -> dict[str, dict[str, Any]]:
        """
        Allocate region work to region agents (greedy colocation), schedule EDF, route.
        Returns action_dict per agent_id for agents in region only.
        """
        from labtrust_gym.baselines.coordination.interface import (
            ACTION_MOVE,
            ACTION_NOOP,
            ACTION_START_RUN,
        )

        zone_ids = region_zone_ids
        device_ids = region_device_ids
        device_zone = region_device_zone
        assignments: list[tuple[str, str, str, int]] = []
        used_work: set[tuple[str, str]] = set()
        worklist: list[tuple[int, str, str, str]] = []
        for _r, work_id, device_id, zone_id, prio, _dl in region_assignments:
            worklist.append((prio, device_id, work_id, zone_id))
        worklist.sort(key=lambda x: (-x[0], x[1], x[2]))
        assigned_agents: set[str] = set()
        for prio, device_id, work_id, zone_id in worklist:
            if (device_id, work_id) in used_work:
                continue
            for agent_id in region_agent_ids:
                if agent_id in assigned_agents:
                    continue
                o = obs.get(agent_id) or {}
                if log_frozen(o):
                    continue
                my_zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""
                if my_zone != zone_id:
                    continue
                assigned_agents.add(agent_id)
                used_work.add((device_id, work_id))
                assignments.append((agent_id, work_id, device_id, prio))
                break

        allocation = AllocationDecision(assignments=tuple(assignments), explain="local")
        per_agent: dict[str, list[tuple[str, int, int]]] = {}
        for agent_id, work_id, device_id, prio in allocation.assignments:
            deadline = t + 20
            if agent_id not in per_agent:
                per_agent[agent_id] = []
            per_agent[agent_id].append((work_id, deadline, prio))
        for aid in per_agent:
            per_agent[aid].sort(key=lambda x: (x[1], -x[2], x[0]))
        per_agent_tuple = tuple((aid, tuple(lst)) for aid, lst in sorted(per_agent.items()))
        schedule = ScheduleDecision(per_agent=per_agent_tuple, explain="edf")

        class LocalCtx:
            agent_ids: list[str]
            zone_ids: list[str]
            device_ids: list[str]
            device_zone: dict[str, str]
            obs: dict[str, Any]
            policy: dict[str, Any]
            t: int
            rng: Any

        ctx = LocalCtx()
        ctx.agent_ids = region_agent_ids
        ctx.zone_ids = zone_ids
        ctx.device_ids = device_ids
        ctx.device_zone = device_zone
        ctx.obs = obs
        ctx.policy = policy
        ctx.t = t
        ctx.rng = rng
        route = self._router.route(cast(KernelContext, ctx), allocation, schedule)

        out: dict[str, dict[str, Any]] = {}
        for agent_id in region_agent_ids:
            out[agent_id] = {"action_index": ACTION_NOOP}
        for agent_id, action_type, args_tuple in route.per_agent:
            args = dict(args_tuple) if args_tuple else {}
            if action_type == "NOOP":
                out[agent_id] = {"action_index": ACTION_NOOP}
            elif action_type == "MOVE":
                out[agent_id] = {
                    "action_index": ACTION_MOVE,
                    "action_type": "MOVE",
                    "args": {
                        "from_zone": args.get("from_zone"),
                        "to_zone": args.get("to_zone"),
                    },
                }
            elif action_type == "START_RUN":
                out[agent_id] = {
                    "action_index": ACTION_START_RUN,
                    "action_type": "START_RUN",
                    "args": {
                        "device_id": args.get("device_id"),
                        "work_id": args.get("work_id"),
                    },
                }
        return out
