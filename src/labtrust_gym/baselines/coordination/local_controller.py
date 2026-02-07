"""
Deterministic local controller: translates high-level assignments (SET_INTENT)
into concrete actions using greedy, EDF, or WHCA strategies.

Used by LLM hierarchical allocator: LLM outputs agent_id -> job_id (and optional
priority weights); this module produces NOOP, TICK, MOVE, QUEUE_RUN, START_RUN, OPEN_DOOR.
Shield still applies to the concrete actions (reduces LLM authority).
"""

from __future__ import annotations

from typing import Any, Literal

from labtrust_gym.baselines.coordination.coordination_kernel import KernelContext
from labtrust_gym.baselines.coordination.decision_types import (
    AllocationDecision,
    RouteDecision,
    ScheduleDecision,
)
from labtrust_gym.baselines.coordination.interface import (
    ACTION_MOVE,
    ACTION_NOOP,
    ACTION_START_RUN,
)
from labtrust_gym.baselines.coordination.kernel_components import (
    EDFScheduler,
    TrivialRouter,
)
from labtrust_gym.baselines.coordination.obs_utils import (
    get_queue_by_device,
    get_zone_from_obs,
    log_frozen,
    queue_has_head,
)
from labtrust_gym.engine.zones import build_adjacency_set

StrategyKind = Literal["greedy", "edf", "whca"]

# Job id format for matching LLM assignment to current queue heads
def _job_id(device_id: str, work_id: str) -> str:
    return f"{device_id}:{work_id}"


def _build_available_work(
    obs: dict[str, Any],
    agent_ids: list[str],
    device_ids: list[str],
    device_zone: dict[str, str],
) -> list[tuple[str, str, str, str, int]]:
    """
    From obs (queue_by_device, device_zone) build list of (job_id, device_id, work_id, zone_id, priority).
    Uses first available agent's obs for queue state; deterministic via sorted device order.
    """
    out: list[tuple[str, str, str, str, int]] = []
    seen: set[tuple[str, str]] = set()
    sample = None
    for aid in sorted(agent_ids):
        if aid in obs and isinstance(obs[aid], dict):
            sample = obs[aid]
            break
    if not sample:
        return out
    qbd = get_queue_by_device(sample)
    for idx, dev_id in enumerate(device_ids):
        if idx >= len(qbd):
            continue
        d = qbd[idx] if isinstance(qbd[idx], dict) else {}
        if not queue_has_head(sample, idx):
            continue
        work_id = str(d.get("queue_head") or "W")
        zone_id = device_zone.get(dev_id, "")
        if (dev_id, work_id) in seen:
            continue
        seen.add((dev_id, work_id))
        prio = 2 if "STAT" in work_id.upper() else (1 if "URGENT" in work_id.upper() else 0)
        out.append((_job_id(dev_id, work_id), dev_id, work_id, zone_id, prio))
    out.sort(key=lambda x: (-x[4], x[1], x[2]))
    return out


def _extract_intents(
    proposal_dict: dict[str, Any],
    agent_ids: list[str],
) -> list[tuple[str, str, int]]:
    """
    Extract (agent_id, job_id, priority_weight) from proposal per_agent where action_type == SET_INTENT.
    """
    intents: list[tuple[str, str, int]] = []
    per_agent = proposal_dict.get("per_agent") or []
    agent_set = set(agent_ids)
    for pa in per_agent:
        if not isinstance(pa, dict):
            continue
        if (pa.get("action_type") or "").strip() != "SET_INTENT":
            continue
        agent_id = pa.get("agent_id")
        if agent_id not in agent_set:
            continue
        args = pa.get("args")
        if not isinstance(args, dict):
            continue
        job_id = str(args.get("job_id") or "").strip()
        if not job_id:
            continue
        pw = args.get("priority_weight")
        if pw is not None and hasattr(pw, "__int__"):
            priority_weight = int(pw)
        else:
            priority_weight = int(args.get("priority_weight", 1))
        intents.append((agent_id, job_id, priority_weight))
    return intents


def _allocation_from_intents(
    intents: list[tuple[str, str, int]],
    available_work: list[tuple[str, str, str, str, int]],
    strategy: StrategyKind,
) -> AllocationDecision:
    """
    Map (agent_id, job_id, priority_weight) to (agent_id, work_id, device_id, prio) using available_work.
    Greedy: use intents order and first match. EDF: sort available_work by priority then match.
    """
    job_to_work: dict[str, tuple[str, str, str, int]] = {
        jid: (dev_id, work_id, zone_id, prio)
        for jid, dev_id, work_id, zone_id, prio in available_work
    }
    assignments: list[tuple[str, str, str, int]] = []
    used_jobs: set[str] = set()
    used_agents: set[str] = set()
    if strategy == "edf":
        intents_sorted = sorted(intents, key=lambda x: (-x[2], x[0], x[1]))
    else:
        intents_sorted = intents
    for agent_id, job_id, priority_weight in intents_sorted:
        if agent_id in used_agents:
            continue
        if job_id in used_jobs:
            continue
        if job_id not in job_to_work:
            continue
        dev_id, work_id, _zone_id, prio = job_to_work[job_id]
        used_agents.add(agent_id)
        used_jobs.add(job_id)
        assignments.append((agent_id, work_id, dev_id, max(prio, priority_weight)))
    return AllocationDecision(assignments=tuple(assignments), explain=f"local_{strategy}")


def intent_to_actions(
    proposal_dict: dict[str, Any],
    obs: dict[str, Any],
    agent_ids: list[str],
    zone_ids: list[str],
    device_ids: list[str],
    device_zone: dict[str, str],
    policy: dict[str, Any],
    t: int,
    seed: int,
    strategy: StrategyKind = "edf",
    use_whca: bool = False,
    whca_horizon: int = 10,
) -> dict[str, dict[str, Any]]:
    """
    Translate CoordinationProposal with SET_INTENT per-agent into concrete action_dict.

    - Extracts (agent_id, job_id, priority_weight) from proposal where action_type == SET_INTENT.
    - Builds available work from obs (queue_by_device + device_zone).
    - Builds AllocationDecision, ScheduleDecision (EDF), RouteDecision (Trivial or WHCA).
    - Returns one action per agent (action_index, action_type, args) for env.step.

    Deterministic for same proposal, obs, seed.
    """
    import random

    rng = random.Random(seed + t)
    intents = _extract_intents(proposal_dict, agent_ids)
    available_work = _build_available_work(obs, agent_ids, device_ids, device_zone)
    allocation = _allocation_from_intents(intents, available_work, strategy)

    per_agent_schedule: dict[str, list[tuple[str, int, int]]] = {}
    for agent_id, work_id, device_id, prio in allocation.assignments:
        deadline = t + 20
        if agent_id not in per_agent_schedule:
            per_agent_schedule[agent_id] = []
        per_agent_schedule[agent_id].append((work_id, deadline, prio))
    for aid in per_agent_schedule:
        per_agent_schedule[aid].sort(key=lambda x: (x[1], -x[2], x[0]))
    schedule = ScheduleDecision(
        per_agent=tuple((aid, tuple(lst)) for aid, lst in sorted(per_agent_schedule.items())),
        explain="edf",
    )

    ctx = KernelContext(
        obs=obs,
        infos={},
        t=t,
        policy=policy,
        scale_config={},
        seed=seed,
        rng=rng,
    )
    if not ctx.zone_ids and zone_ids:
        object.__setattr__(ctx, "zone_ids", zone_ids)
    if not ctx.device_ids and device_ids:
        object.__setattr__(ctx, "device_ids", device_ids)
    if not ctx.device_zone and device_zone:
        object.__setattr__(ctx, "device_zone", device_zone)
    layout = (policy or {}).get("zone_layout") or {}
    adjacency = build_adjacency_set(layout.get("graph_edges") or [])
    object.__setattr__(ctx, "adjacency", adjacency)

    if use_whca and strategy == "whca":
        try:
            from labtrust_gym.baselines.coordination.kernel_components import WHCARouter
            router = WHCARouter(horizon=whca_horizon)
            router.reset(seed)
            route = router.route(ctx, allocation, schedule)
        except Exception:
            router = TrivialRouter()
            route = router.route(ctx, allocation, schedule)
    else:
        router = TrivialRouter()
        route = router.route(ctx, allocation, schedule)

    out: dict[str, dict[str, Any]] = {aid: {"action_index": ACTION_NOOP, "action_type": "NOOP"} for aid in agent_ids}
    for agent_id, action_type, args_tuple in route.per_agent:
        args = dict(args_tuple) if args_tuple else {}
        if action_type == "NOOP":
            out[agent_id] = {"action_index": ACTION_NOOP, "action_type": "NOOP"}
        elif action_type == "MOVE":
            out[agent_id] = {
                "action_index": ACTION_MOVE,
                "action_type": "MOVE",
                "args": {"from_zone": args.get("from_zone"), "to_zone": args.get("to_zone")},
            }
        elif action_type == "START_RUN":
            out[agent_id] = {
                "action_index": ACTION_START_RUN,
                "action_type": "START_RUN",
                "args": {"device_id": args.get("device_id"), "work_id": args.get("work_id")},
            }
        else:
            out[agent_id] = {"action_index": ACTION_NOOP, "action_type": "NOOP"}
    return out
