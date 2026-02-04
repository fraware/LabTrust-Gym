"""
Hierarchical coordination method: HubPlanner (macro assign to regions) + LocalControllers
(EDF + route per region). Handoff protocol for ACK/escalation. Integrates with blackboard/views:
locals can use local view_snapshots; hub uses global obs or aggregated summary.
Deterministic; no new deps.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from labtrust_gym.baselines.coordination.coordination_kernel import KernelContext
from labtrust_gym.baselines.coordination.interface import (
    ACTION_NOOP,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.obs_utils import get_zone_from_obs
from labtrust_gym.engine.zones import build_adjacency_set

from labtrust_gym.baselines.coordination.hierarchical.region_partition import (
    partition_zones_into_regions,
)
from labtrust_gym.baselines.coordination.hierarchical.hub_planner import (
    HubPlanner,
)
from labtrust_gym.baselines.coordination.hierarchical.local_controller import (
    LocalController,
)
from labtrust_gym.baselines.coordination.hierarchical.handoff import (
    HandoffProtocol,
    HUB_REGION_ID,
)


def _build_region_index(
    zone_to_region: Dict[str, str],
    agent_ids: List[str],
    obs: Dict[str, Any],
    zone_ids: List[str],
    device_ids: List[str],
    device_zone: Dict[str, str],
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], Dict[str, List[str]], Set[str]]:
    """Agents, zones, devices per region; set of region_ids."""
    agents_per_region: Dict[str, List[str]] = defaultdict(list)
    zones_per_region: Dict[str, List[str]] = defaultdict(list)
    devices_per_region: Dict[str, List[str]] = defaultdict(list)
    for zid, rid in zone_to_region.items():
        zones_per_region[rid].append(zid)
    for zid in zone_ids:
        rid = zone_to_region.get(zid, "R_0")
        if zid not in zones_per_region[rid]:
            zones_per_region[rid].append(zid)
    for agent_id in agent_ids:
        o = obs.get(agent_id) or {}
        my_zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""
        rid = zone_to_region.get(my_zone, "R_0")
        agents_per_region[rid].append(agent_id)
    for dev_id, zid in device_zone.items():
        rid = zone_to_region.get(zid, "R_0")
        devices_per_region[rid].append(dev_id)
    region_ids = set(agents_per_region.keys()) | set(zones_per_region.keys())
    return agents_per_region, zones_per_region, devices_per_region, region_ids


class HierarchicalHubLocal(CoordinationMethod):
    """
    Hub assigns work to regions; local controllers schedule and route within region.
    Handoff: hub->region assignment with ACK deadline; missing ACK triggers escalation.
    Metrics: hierarchy.cross_region_handoffs, handoff_fail_rate, escalations.
    """

    def __init__(
        self,
        ack_deadline_steps: int = 10,
        sla_horizon: int = 20,
    ) -> None:
        self._ack_deadline_steps = ack_deadline_steps
        self._sla_horizon = sla_horizon
        self._hub = HubPlanner(sla_horizon=sla_horizon)
        self._handoff = HandoffProtocol(ack_deadline_steps=ack_deadline_steps)
        self._local = LocalController(use_whca=False)
        self._zone_to_region: Dict[str, str] = {}
        self._policy: Dict[str, Any] = {}
        self._scale_config: Dict[str, Any] = {}
        self._seed = 0
        self._last_hierarchy_metrics: Dict[str, Any] = {}

    @property
    def method_id(self) -> str:
        return "hierarchical_hub_local"

    def reset(
        self,
        seed: int,
        policy: Dict[str, Any],
        scale_config: Dict[str, Any],
    ) -> None:
        self._seed = seed
        self._policy = policy or {}
        self._scale_config = scale_config or {}
        zone_ids = []
        layout = (self._policy or {}).get("zone_layout") or {}
        for z in layout.get("zones") or []:
            if isinstance(z, dict) and z.get("zone_id"):
                zone_ids.append(z["zone_id"])
        if not zone_ids:
            zone_ids = list(set())
        self._zone_to_region = partition_zones_into_regions(
            zone_ids,
            policy=self._policy,
            scale_config=self._scale_config,
        )
        self._handoff = HandoffProtocol(ack_deadline_steps=self._ack_deadline_steps)

    def step(
        self, context: KernelContext
    ) -> Tuple[Dict[str, Dict[str, Any]], Optional[CoordinationDecision]]:
        obs = context.obs or {}
        t = context.t
        zone_ids = list(context.zone_ids or [])
        device_ids = list(context.device_ids or [])
        device_zone = dict(context.device_zone or {})
        policy = context.policy or {}
        rng = context.rng
        agent_ids = list(context.agent_ids or [])
        if not self._zone_to_region and zone_ids:
            self._zone_to_region = partition_zones_into_regions(
                zone_ids,
                policy=policy,
                scale_config=context.scale_config or {},
            )
        zone_to_region = self._zone_to_region
        (
            agents_per_region,
            zones_per_region,
            devices_per_region,
            region_ids,
        ) = _build_region_index(
            zone_to_region, agent_ids, obs, zone_ids, device_ids, device_zone
        )
        layout = (policy or {}).get("zone_layout") or {}
        adjacency = build_adjacency_set(layout.get("graph_edges") or [])

        still_pending, escalated = self._handoff.tick(t)
        escalated_work: Set[Tuple[str, str]] = set(
            (e.work_id, e.device_id) for e in escalated
        )

        macro = self._hub.assign(obs, zone_to_region, device_zone, device_ids, t, rng)
        region_assignments: Dict[str, List[Tuple[str, str, str, str, int, int]]] = (
            defaultdict(list)
        )
        for region_id, work_id, device_id, zone_id, prio, deadline in macro:
            if (work_id, device_id) in escalated_work:
                continue
            region_assignments[region_id].append(
                (region_id, work_id, device_id, zone_id, prio, deadline)
            )
            if not self._handoff.has_pending(work_id, device_id, region_id):
                self._handoff.create_handoff(
                    work_id, device_id, HUB_REGION_ID, region_id, zone_id, t, prio
                )

        for rid in sorted(region_ids):
            seen_rid = {(a[2], a[1]) for a in region_assignments[rid]}
            for ev in self._handoff.pending_for_region(rid):
                if (ev.device_id, ev.work_id) not in seen_rid:
                    seen_rid.add((ev.device_id, ev.work_id))
                    region_assignments[rid].append(
                        (
                            rid,
                            ev.work_id,
                            ev.device_id,
                            ev.zone_id,
                            ev.priority,
                            ev.ack_by_t,
                        )
                    )

        actions: Dict[str, Dict[str, Any]] = {
            aid: {"action_index": ACTION_NOOP} for aid in agent_ids
        }
        for rid in sorted(region_ids):
            ragents = sorted(agents_per_region.get(rid, []))
            rzones = sorted(zones_per_region.get(rid, []))
            rdevices = sorted(devices_per_region.get(rid, []))
            rdevice_zone = {d: device_zone.get(d, "") for d in rdevices}
            rassign = region_assignments.get(rid, [])
            region_obs = {aid: obs[aid] for aid in ragents if aid in obs}
            if not region_obs:
                continue
            sub_actions = self._local.step(
                rid,
                ragents,
                rzones,
                rdevices,
                rdevice_zone,
                region_obs,
                rassign,
                policy,
                adjacency,
                t,
                context.seed,
                rng,
            )
            for aid, ad in sub_actions.items():
                actions[aid] = ad
                if ad.get("action_type") == "START_RUN":
                    args = ad.get("args") or {}
                    self._handoff.ack(
                        args.get("work_id", ""),
                        args.get("device_id", ""),
                        t,
                    )

        self._last_hierarchy_metrics = self._handoff.get_metrics()
        return actions, None

    def propose_actions(
        self,
        obs: Dict[str, Any],
        infos: Dict[str, Dict[str, Any]],
        t: int,
    ) -> Dict[str, Dict[str, Any]]:
        import random

        from labtrust_gym.baselines.coordination.compose import build_kernel_context

        policy = self._policy
        scale_config = self._scale_config
        seed = self._seed
        rng = random.Random(seed + t)
        ctx = KernelContext(
            obs=obs,
            infos=infos or {},
            t=t,
            policy=policy,
            scale_config=scale_config,
            seed=seed,
            rng=rng,
        )
        actions, _ = self.step(ctx)
        return actions

    def get_hierarchy_metrics(self) -> Dict[str, Any]:
        return dict(self._last_hierarchy_metrics)
