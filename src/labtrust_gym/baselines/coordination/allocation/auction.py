"""
Sealed-bid auction allocator: agents bid for work items; assignment by lowest cost.
Congestion-aware pricing; RBAC/token constraints; strict bid budget.
Deterministic: stable ordering, seeded tie-breaks.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Cost sentinel for "cannot bid" (RBAC/token forbidden)
BID_FORBIDDEN = 1e9

# Zone requiring token for entry (from token_enforcement_map / zone_layout)
RESTRICTED_ZONE_IDS: set[str] = {"Z_RESTRICTED_BIOHAZARD"}


@dataclass
class WorkItem:
    """One work item (queue head) to assign."""

    work_id: str
    device_id: str
    zone_id: str
    priority: int  # 2=STAT, 1=URGENT, 0=ROUTINE


@dataclass
class PriceSignals:
    """Congestion and queue pricing for bid computation."""

    zone_congestion: dict[str, float] = field(default_factory=dict)
    device_queue_price: dict[str, float] = field(default_factory=dict)


def _path_length(
    start: str,
    goal: str,
    adjacency: set[tuple[str, str]],
) -> int:
    """BFS path length; returns large int if unreachable."""
    if start == goal:
        return 0
    seen: set[str] = {start}
    queue: list[tuple[str, int]] = [(start, 0)]
    while queue:
        node, dist = queue.pop(0)
        for a, b in adjacency:
            if a != node or b in seen:
                continue
            seen.add(b)
            if b == goal:
                return dist + 1
            queue.append((b, dist + 1))
    return 999


def compute_bid(
    agent_id: str,
    item: WorkItem,
    view: dict[str, Any],
    price_signals: PriceSignals,
    adjacency: set[tuple[str, str]],
    agent_zone: str,
    agent_queue_load: int,
    energy_proxy: float = 0.0,
) -> float:
    """
    Bid cost for (agent, item). Lower = better.
    Combines: distance-to-work, queue load, congestion price, device queue price, energy proxy.
    Returns BID_FORBIDDEN if view indicates agent cannot perform (caller filters by RBAC).
    """
    dist = _path_length(agent_zone, item.zone_id, adjacency)
    if dist >= 999:
        return BID_FORBIDDEN
    zone_price = price_signals.zone_congestion.get(item.zone_id, 0.0)
    device_price = price_signals.device_queue_price.get(item.device_id, 0.0)
    cost = (
        float(dist) * 10.0
        + float(agent_queue_load) * 2.0
        + zone_price
        + device_price
        + energy_proxy
        - item.priority * 5.0
    )
    return max(0.0, cost)


def build_price_signals(
    obs: dict[str, dict[str, Any]],
    device_zone: dict[str, str],
    zone_ids: list[str],
    device_ids: list[str],
) -> PriceSignals:
    """
    Congestion per zone (agent count in zone), device queue price (queue depth + priority mix).
    """
    zone_count: dict[str, float] = defaultdict(float)
    for o in obs.values():
        if isinstance(o, dict):
            z = o.get("zone_id") or ""
            if z:
                zone_count[z] += 1.0
    zone_congestion = {z: zone_count.get(z, 0.0) * 1.0 for z in zone_ids}

    device_queue_price: dict[str, float] = {}
    for dev_id in device_ids:
        total = 0.0
        for o in obs.values():
            qbd = (o or {}).get("queue_by_device") or []
            for i, d in enumerate(qbd):
                if not isinstance(d, dict):
                    continue
                dev_in_list = d.get("device_id") or (device_ids[i] if i < len(device_ids) else "")
                if dev_in_list != dev_id:
                    continue
                qlen = int(d.get("queue_len") or 0)
                head = str(d.get("queue_head") or "")
                prio = 2 if "STAT" in head.upper() else (1 if "URGENT" in head.upper() else 0)
                total += qlen * 1.0 + prio * 2.0
        device_queue_price[dev_id] = total
    return PriceSignals(
        zone_congestion=dict(zone_congestion),
        device_queue_price=dict(device_queue_price),
    )


def _restricted_zone_ids_from_policy(policy: dict[str, Any]) -> set[str]:
    """Zones that require token for entry (zone_layout.zones with restricted=true)."""
    out: set[str] = set(RESTRICTED_ZONE_IDS)
    layout = (policy or {}).get("zone_layout") or {}
    for z in layout.get("zones") or []:
        if isinstance(z, dict) and z.get("restricted") and z.get("zone_id"):
            out.add(str(z["zone_id"]))
    return out


def _agent_role_allows_start_run(policy: dict[str, Any], agent_id: str) -> bool:
    """True if agent's role has START_RUN in allowed_actions (RBAC)."""
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


def _agent_has_restricted_entry_token(obs: dict[str, Any]) -> bool:
    """True if obs indicates agent has TOKEN_RESTRICTED_ENTRY."""
    token_active = obs.get("token_active")
    if not isinstance(token_active, dict):
        return False
    return bool(token_active.get("TOKEN_RESTRICTED_ENTRY"))


def agent_can_start_run_at_device(
    agent_id: str,
    device_id: str,
    zone_id: str,
    policy: dict[str, Any],
    obs: dict[str, Any],
    restricted_zones: set[str],
) -> bool:
    """
    True if agent is allowed to perform START_RUN at device (RBAC + token for restricted zone).
    Caller provides obs for that agent and restricted_zones from policy.
    """
    if not _agent_role_allows_start_run(policy, agent_id):
        return False
    if zone_id in restricted_zones and not _agent_has_restricted_entry_token(obs):
        return False
    return True


REASON_CODE_BID_ANOMALY = "BID_ANOMALY_SPOOF_SUSPECTED"
INJ_BID_SPOOF_001 = "INJ-BID-SPOOF-001"
CONTAINMENT_STEPS_K = 5


def detect_bid_anomalies(
    bids_used: list[tuple[str, str, float]],
    threshold_std: float = 2.0,
) -> tuple[set[str], list[dict[str, Any]]]:
    """
    Flag agents whose winning bid is anomalously low (below mean - threshold_std * std).
    Returns (set of agent_ids to contain, list of emit payloads with reason_code).
    """
    if len(bids_used) < 2:
        return set(), []
    bids_only = [b[2] for b in bids_used]
    mean_bid = sum(bids_only) / len(bids_only)
    variance = sum((x - mean_bid) ** 2 for x in bids_only) / len(bids_only)
    std = (variance**0.5) if variance > 0 else 0.0
    if std == 0:
        return set(), []
    threshold = mean_bid - threshold_std * std
    excluded: set[str] = set()
    emits: list[dict[str, Any]] = []
    for agent_id, work_id, bid in bids_used:
        if bid < threshold:
            excluded.add(agent_id)
            emits.append(
                {
                    "emit": "BID_ANOMALY_DETECTED",
                    "agent_id": agent_id,
                    "work_id": work_id,
                    "bid": bid,
                    "mean_bid": round(mean_bid, 4),
                    "reason_code": REASON_CODE_BID_ANOMALY,
                }
            )
    return excluded, emits


def gini_coefficient(work_per_agent: dict[str, int]) -> float:
    """
    Gini coefficient for work distribution (0 = perfectly equal, 1 = maximally unequal).
    Uses sorted values; deterministic.
    """
    if not work_per_agent:
        return 0.0
    counts = sorted(work_per_agent.values())
    n = len(counts)
    if n == 0:
        return 0.0
    cumul = 0.0
    for i, v in enumerate(counts):
        cumul += (2 * (i + 1) - n - 1) * v
    total = sum(counts)
    if total == 0:
        return 0.0
    return float(cumul) / (n * total)


def run_auction(
    items: list[WorkItem],
    agents: list[str],
    bid_fn: Callable[[str, WorkItem], float],
    max_bids: int,
    rng: Any,
) -> tuple[list[tuple[str, str, str, int]], list[tuple[str, str, float]], dict[str, Any]]:
    """
    Sealed-bid auction: each agent bids for each item; assign item to lowest bidder.
    One item per agent per round; max_bids caps total assignments.
    Returns (assignments, all_bids_used, metrics).
    assignments: (agent_id, work_id, device_id, priority)
    all_bids_used: (agent_id, work_id, bid) for winning bids.
    Deterministic: items and agents sorted; tie-break with rng.
    """
    assignments: list[tuple[str, str, str, int]] = []
    bids_used: list[tuple[str, str, float]] = []
    all_bids_list: list[float] = []
    rebids = 0

    sorted_items = sorted(
        items,
        key=lambda x: (-x.priority, x.device_id, x.work_id),
    )
    sorted_agents = sorted(agents)
    assigned_agents: set[str] = set()
    used_work: set[tuple[str, str]] = set()
    bids_budget = max_bids

    for item in sorted_items:
        if bids_budget <= 0:
            break
        if (item.device_id, item.work_id) in used_work:
            continue
        candidate_bids: list[tuple[float, str, int]] = []
        for idx, agent_id in enumerate(sorted_agents):
            if agent_id in assigned_agents:
                continue
            bid = bid_fn(agent_id, item)
            if bid >= BID_FORBIDDEN:
                continue
            tie = rng.randint(0, 999) if rng else 0
            candidate_bids.append((bid, agent_id, tie))
        if not candidate_bids:
            continue
        candidate_bids.sort(key=lambda x: (x[0], x[2], x[1]))
        best_bid, winner, _ = candidate_bids[0]
        assigned_agents.add(winner)
        used_work.add((item.device_id, item.work_id))
        assignments.append((winner, item.work_id, item.device_id, item.priority))
        bids_used.append((winner, item.work_id, best_bid))
        all_bids_list.append(best_bid)
        bids_budget -= 1

    mean_bid = sum(all_bids_list) / len(all_bids_list) if all_bids_list else 0.0
    metrics: dict[str, Any] = {
        "mean_bid": round(mean_bid, 4),
        "rebid_rate": rebids / max(1, len(items)),
        "num_assignments": len(assignments),
    }
    return assignments, bids_used, metrics


class AuctionAllocator:
    """
    Allocator that runs a sealed-bid auction over work items.
    Respects RBAC and token constraints; uses congestion-aware price signals.
    Optional bid anomaly detector: flags outlier low bids, containment for K steps.
    INJ-BID-SPOOF-001: when injection_id set in scale_config, designated agent bids artificially low.
    Exposes alloc metrics (gini_work_distribution, mean_bid, rebid_rate) and last_emits.
    """

    def __init__(
        self,
        max_bids: int | None = None,
        detector_enabled: bool = True,
        containment_steps: int = CONTAINMENT_STEPS_K,
    ) -> None:
        self._max_bids = max_bids
        self._detector_enabled = detector_enabled
        self._containment_steps = containment_steps
        self._last_metrics: dict[str, Any] = {}
        self._excluded_until_step: dict[str, int] = {}
        self._last_emits: list[dict[str, Any]] = []

    def allocate(self, context: Any) -> Any:
        from labtrust_gym.baselines.coordination.coordination_kernel import (
            KernelContext,
        )
        from labtrust_gym.baselines.coordination.decision_types import (
            AllocationDecision,
        )
        from labtrust_gym.baselines.coordination.obs_utils import (
            get_queue_by_device,
            get_zone_from_obs,
            log_frozen,
            queue_has_head,
        )

        if not isinstance(context, KernelContext):
            return AllocationDecision(explain="auction_invalid_context")
        agents = list(context.agent_ids or [])
        zone_ids = list(context.zone_ids or [])
        device_ids = list(context.device_ids or [])
        device_zone = dict(context.device_zone or {})
        adjacency = context.adjacency or set()
        policy = context.policy or {}
        obs = context.obs or {}
        rng = context.rng
        scale_config = context.scale_config or {}
        max_bids = (
            self._max_bids
            if self._max_bids is not None
            else int(scale_config.get("max_bids_per_step", 0)) or max(len(agents) * 2, 1)
        )
        restricted_zones = _restricted_zone_ids_from_policy(policy)
        t = context.t
        for aid in list(self._excluded_until_step.keys()):
            if t > self._excluded_until_step[aid]:
                del self._excluded_until_step[aid]
        excluded_this_step = {aid for aid, until in self._excluded_until_step.items() if t <= until}
        injection_id = (scale_config or {}).get("injection_id") or ""
        spoof_agent_id = (scale_config or {}).get("spoof_agent_id")
        if injection_id == INJ_BID_SPOOF_001 and not spoof_agent_id and agents:
            spoof_agent_id = sorted(agents)[0]

        work_items: list[WorkItem] = []
        seen_work: set[tuple[str, str]] = set()
        for agent_id in agents:
            o = obs.get(agent_id) or {}
            if log_frozen(o):
                continue
            qbd = get_queue_by_device(o)
            for idx, dev_id in enumerate(device_ids):
                if idx >= len(qbd):
                    continue
                if not queue_has_head(o, idx):
                    continue
                dev_zone = device_zone.get(dev_id, "")
                head = (qbd[idx] or {}).get("queue_head", "W")
                prio = 2 if "STAT" in str(head).upper() else (1 if "URGENT" in str(head).upper() else 0)
                key = (dev_id, head or "W")
                if key in seen_work:
                    continue
                seen_work.add(key)
                work_items.append(
                    WorkItem(
                        work_id=head or "W",
                        device_id=dev_id,
                        zone_id=dev_zone,
                        priority=prio,
                    )
                )

        price_signals = build_price_signals(obs, device_zone, zone_ids, device_ids)
        view_snapshots = getattr(context, "view_snapshots", None) or {}

        def bid_fn(agent_id: str, item: WorkItem) -> float:
            if agent_id in excluded_this_step:
                return BID_FORBIDDEN
            o = obs.get(agent_id) or {}
            agent_zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""
            if not agent_can_start_run_at_device(
                agent_id,
                item.device_id,
                item.zone_id,
                policy,
                o,
                restricted_zones,
            ):
                return BID_FORBIDDEN
            view = view_snapshots.get(agent_id) or o
            qbd = get_queue_by_device(o)
            load = sum(int((d or {}).get("queue_len", 0)) for d in qbd if isinstance(d, dict))
            energy_proxy = 0.0
            raw_bid = compute_bid(
                agent_id,
                item,
                view,
                price_signals,
                adjacency,
                agent_zone,
                load,
                energy_proxy,
            )
            if (
                injection_id == INJ_BID_SPOOF_001
                and spoof_agent_id
                and agent_id == spoof_agent_id
                and raw_bid < BID_FORBIDDEN
            ):
                return max(0.0, raw_bid * 0.1)
            return raw_bid

        assignments, bids_used, metrics = run_auction(work_items, agents, bid_fn, max_bids, rng)
        detector_enabled = scale_config.get("detector_enabled", self._detector_enabled)
        if detector_enabled and bids_used:
            threshold_std = 0.5 if len(bids_used) <= 3 else 2.0
            excluded_set, emits = detect_bid_anomalies(bids_used, threshold_std=threshold_std)
            self._last_emits = list(emits)
            for aid in excluded_set:
                self._excluded_until_step[aid] = t + self._containment_steps
        else:
            self._last_emits = []
        work_per_agent: dict[str, int] = defaultdict(int)
        for agent_id, _work_id, _dev_id, _prio in assignments:
            work_per_agent[agent_id] += 1
        gini = gini_coefficient(dict(work_per_agent))
        self._last_metrics = {
            "gini_work_distribution": round(gini, 4),
            "mean_bid": metrics.get("mean_bid", 0.0),
            "rebid_rate": metrics.get("rebid_rate", 0.0),
            "num_assignments": metrics.get("num_assignments", 0),
            "alloc_emits": self._last_emits,
        }
        explain = f"auction n={len(assignments)} gini={gini:.2f}"
        return AllocationDecision(
            assignments=tuple(assignments),
            explain=explain,
        )

    def get_alloc_metrics(self) -> dict[str, Any]:
        """Last-step allocator metrics for results coordination block."""
        return dict(self._last_metrics)
