"""
Compose allocator + scheduler + router into a CoordinationMethod.

Returns a method that implements step(context) -> (actions, CoordinationDecision)
and propose_actions(obs, infos, t) for backward compatibility.
"""  # noqa: D205

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.coordination.coordination_kernel import (
    Allocator,
    KernelContext,
    Router,
    Scheduler,
)
from labtrust_gym.baselines.coordination.decision_types import CoordinationDecision
from labtrust_gym.baselines.coordination.interface import (
    ACTION_MOVE,
    ACTION_NOOP,
    ACTION_START_RUN,
    ACTION_TICK,
    CoordinationMethod,
)


def _stable_hash(obj: Any) -> str:
    try:
        payload = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        payload = repr(obj)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _route_to_action_dict(
    agent_id: str,
    action_type: str,
    args_tuple: tuple[tuple[str, Any], ...],
) -> dict[str, Any]:
    """Convert route (action_type, args_tuple) to action_dict for env."""
    args = dict(args_tuple) if args_tuple else {}
    if action_type == "NOOP":
        return {"action_index": ACTION_NOOP}
    if action_type == "MOVE":
        return {
            "action_index": ACTION_MOVE,
            "action_type": "MOVE",
            "args": {
                "from_zone": args.get("from_zone"),
                "to_zone": args.get("to_zone"),
            },
        }
    if action_type == "START_RUN":
        return {
            "action_index": ACTION_START_RUN,
            "action_type": "START_RUN",
            "args": {
                "device_id": args.get("device_id"),
                "work_id": args.get("work_id"),
            },
        }
    if action_type == "TICK":
        return {"action_index": ACTION_TICK}
    return {"action_index": ACTION_NOOP}


def compose_kernel(
    allocator: Allocator,
    scheduler: Scheduler,
    router: Router,
    method_id: str,
) -> CoordinationMethod:
    """
    Compose allocator, scheduler, router into a CoordinationMethod.
    Returned method implements step(context) -> (actions, CoordinationDecision)
    and propose_actions(obs, infos, t) (builds context, returns actions only).
    """

    class ComposedKernelMethod(CoordinationMethod):
        def __init__(self) -> None:
            self._allocator = allocator
            self._scheduler = scheduler
            self._router = router
            self._method_id = method_id
            self._seed = 0
            self._policy: dict[str, Any] = {}
            self._scale_config: dict[str, Any] = {}

        @property
        def method_id(self) -> str:
            return self._method_id

        def reset(
            self,
            seed: int,
            policy: dict[str, Any],
            scale_config: dict[str, Any],
        ) -> None:
            self._seed = seed
            self._policy = policy or {}
            self._scale_config = scale_config or {}
            reset_fn = getattr(self._router, "reset", None)
            if callable(reset_fn):
                reset_fn(seed)
            sched_reset = getattr(self._scheduler, "reset", None)
            if callable(sched_reset):
                sched_reset(seed)

        def step(
            self,
            context: KernelContext,
        ) -> tuple[dict[str, dict[str, Any]], CoordinationDecision | None]:
            alloc = self._allocator.allocate(context)
            sched = self._scheduler.schedule(context, alloc)
            route = self._router.route(context, alloc, sched)

            allocation_hash = _stable_hash(alloc.assignments)
            schedule_hash = _stable_hash(sched.per_agent)
            route_hash = _stable_hash(route.per_agent)

            decision = CoordinationDecision(
                method_id=self._method_id,
                step_idx=context.t,
                seed=context.seed,
                state_hash=context.state_hash,
                allocation_hash=allocation_hash,
                schedule_hash=schedule_hash,
                route_hash=route_hash,
                allocation=alloc,
                schedule=sched,
                route=route,
                explain_allocation=alloc.explain,
                explain_schedule=sched.explain,
                explain_route=route.explain,
            )

            actions: dict[str, dict[str, Any]] = {}
            for agent_id in context.agent_ids:
                actions[agent_id] = {"action_index": ACTION_NOOP}
            for agent_id, action_type, args_tuple in route.per_agent:
                actions[agent_id] = _route_to_action_dict(agent_id, action_type, args_tuple)
            for agent_id in context.agent_ids:
                if agent_id not in actions:
                    actions[agent_id] = {"action_index": ACTION_NOOP}

            trace_path = (context.scale_config or {}).get("trace_path")
            if trace_path is not None:
                try:
                    from labtrust_gym.baselines.coordination.trace import (
                        append_trace_event,
                        trace_from_contract_record,
                    )
                    path = Path(trace_path) if isinstance(trace_path, str) else trace_path
                    event = trace_from_contract_record(
                        self._method_id, context.t, actions
                    )
                    append_trace_event(path, event)
                except Exception:
                    pass

            return actions, decision

        def get_route_metrics(self) -> dict[str, Any] | None:
            """Route metrics from router if available (e.g. WHCARouter)."""
            fn = getattr(self._router, "get_route_metrics", None)
            return fn() if callable(fn) else None

        def get_last_planned_path(
            self,
        ) -> (
            tuple[
                list[tuple[str, int, str]],
                list[tuple[str, int, str, str]],
                set[tuple[str, str]],
                dict[str, bool],
            ]
            | None
        ):
            """
            Return (planned_nodes, planned_moves, restricted_edges, agent_has_token)
            from the last step when the router exposed planned path; else None.
            """
            fn = getattr(self._router, "get_last_planned_path", None)
            return fn() if callable(fn) else None

        def get_alloc_metrics(self) -> dict[str, Any] | None:
            """Allocator metrics if available (e.g. AuctionAllocator: gini, mean_bid, rebid_rate)."""
            fn = getattr(self._allocator, "get_alloc_metrics", None)
            return fn() if callable(fn) else None

        def get_schedule_metrics(self) -> dict[str, Any] | None:
            """Schedule metrics if available (e.g. ORScheduler: mean_plan_time_ms, replan_rate)."""
            fn = getattr(self._scheduler, "get_schedule_metrics", None)
            return fn() if callable(fn) else None

        def propose_actions(
            self,
            obs: dict[str, Any],
            infos: dict[str, dict[str, Any]],
            t: int,
        ) -> dict[str, dict[str, Any]]:
            import random

            rng = random.Random(self._seed + t)
            context = KernelContext(
                obs=obs,
                infos=infos,
                t=t,
                policy=self._policy,
                scale_config=self._scale_config,
                seed=self._seed,
                rng=rng,
            )
            actions, _ = self.step(context)
            return actions

    return ComposedKernelMethod()


def build_kernel_context(
    obs: dict[str, Any],
    infos: dict[str, dict[str, Any]],
    t: int,
    policy: dict[str, Any],
    scale_config: dict[str, Any],
    episode_seed: int,
    blackboard_harness: Any | None = None,
) -> KernelContext:
    """Build KernelContext for runner (single place for consistency)."""  # noqa: D205
    import random

    rng = random.Random(episode_seed + t)
    global_log = None
    view_snapshots: dict[str, dict[str, Any]] = {}
    if blackboard_harness is not None:
        global_log = blackboard_harness.global_log
        view_snapshots = blackboard_harness.view_snapshots()
    return KernelContext(
        obs=obs,
        infos=infos,
        t=t,
        policy=policy,
        scale_config=scale_config,
        seed=episode_seed,
        rng=rng,
        global_log=global_log,
        view_snapshots=view_snapshots,
    )
