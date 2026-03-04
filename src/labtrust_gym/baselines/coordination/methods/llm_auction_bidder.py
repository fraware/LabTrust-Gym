"""
Market-based coordinator: LLM produces typed bids only (value, units, constraints);
deterministic auction clears assignments; deterministic dispatcher produces actions.
Strict bid validation. Metrics: bid_skew, gini_work_distribution,
collusion_suspected_proxy. Evaluated under collusion and comms poison injection.

Envelope (SOTA audit):
  - Typical steps per episode: N/A; horizon-driven.
  - LLM calls per step: 1 per agent (bid round), then deterministic clear.
  - Fallback on timeout/refusal: NOOP or minimal valid bid per agent.
  - max_latency_ms: N/A for live; bounded in llm_offline by deterministic backend.
"""

from __future__ import annotations

import logging
import os
import random
from typing import Any

_LOG = logging.getLogger(__name__)

from labtrust_gym.baselines.coordination.interface import (
    ACTION_MOVE,
    ACTION_NOOP,
    ACTION_START_RUN,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.market.auction import (
    TypedBid,
    WorkItem,
    clear_auction,
    validate_bid,
)
from labtrust_gym.baselines.coordination.obs_utils import (
    extract_zone_and_device_ids,
    get_queue_by_device,
    get_zone_from_obs,
    log_frozen,
    queue_has_head,
)
from labtrust_gym.baselines.coordination.state_digest import build_state_digest
from labtrust_gym.engine.zones import build_adjacency_set


def _bfs_next_zone(
    start: str,
    goal: str,
    adjacency: set[tuple[str, str]],
) -> str | None:
    """Next zone from start toward goal. Deterministic."""
    if start == goal:
        return None
    seen: set[str] = {start}
    queue: list[tuple[str, list[str]]] = [(start, [])]
    while queue:
        node, path = queue.pop(0)
        neighbors = sorted([b for (a, b) in adjacency if a == node and b not in seen])
        for n in neighbors:
            seen.add(n)
            new_path = path + [n]
            if n == goal:
                return new_path[0] if new_path else None
            queue.append((n, new_path))
    return None


def _build_work_items(
    obs: dict[str, Any],
    device_ids: list[str],
    device_zone: dict[str, str],
) -> list[WorkItem]:
    """Build work items from obs (queue_by_device with queue_head)."""
    items: list[WorkItem] = []
    seen: set[tuple[str, str]] = set()
    sample = next(iter(obs.values())) if obs else {}
    if not isinstance(sample, dict):
        return items
    qbd = get_queue_by_device(sample)
    for idx, dev_id in enumerate(device_ids):
        if idx >= len(qbd):
            continue
        if not queue_has_head(sample, idx):
            continue
        d = qbd[idx] if isinstance(qbd[idx], dict) else {}
        work_id = str(d.get("queue_head") or "W")
        zone_id = device_zone.get(dev_id, "")
        if (dev_id, work_id) in seen:
            continue
        seen.add((dev_id, work_id))
        prio = 2 if "STAT" in work_id.upper() else (1 if "URGENT" in work_id.upper() else 0)
        items.append(
            WorkItem(
                work_id=work_id,
                device_id=dev_id,
                zone_id=zone_id,
                priority=prio,
            )
        )
    return items


def _proposal_market_to_typed_bids(
    market: list[dict[str, Any]],
    agent_ids: set[str],
) -> tuple[list[TypedBid], list[str]]:
    """
    Parse proposal market[] into TypedBid list. Strict validation.
    Returns (valid_bids, list of validation errors).
    """
    bids: list[TypedBid] = []
    errors: list[str] = []
    for i, m in enumerate(market or []):
        if not isinstance(m, dict):
            errors.append(f"market[{i}] not object")
            continue
        agent_id = m.get("agent_id")
        if not agent_id or agent_id not in agent_ids:
            errors.append(f"market[{i}] invalid or unknown agent_id")
            continue
        bundle = m.get("bundle")
        if isinstance(bundle, dict):
            dev = bundle.get("device_id") or bundle.get("device")
            work = bundle.get("work_id") or bundle.get("work")
            bundle_id = f"{dev}:{work}" if dev and work else ""
        else:
            bundle_id = str(bundle or "").strip()
        if not bundle_id:
            errors.append(f"market[{i}] missing bundle or bundle_id")
            continue
        raw_value = m.get("bid")
        travel_time_estimate = None
        queue_delay_estimate = None
        risk_penalty = None
        fairness_penalty = None
        if isinstance(raw_value, dict):
            value = raw_value.get("value", raw_value.get("cost", 0.0))
            units = raw_value.get("units", "cost")
            travel_time_estimate = raw_value.get("travel_time_estimate")
            queue_delay_estimate = raw_value.get("queue_delay_estimate")
            risk_penalty = raw_value.get("risk_penalty")
            fairness_penalty = raw_value.get("fairness_penalty")
        else:
            value = raw_value
            units = m.get("units", "cost")
        constraints = m.get("constraints")
        if not isinstance(constraints, dict):
            constraints = {}
        ok, err = validate_bid(value, units, constraints=constraints)
        if not ok:
            errors.append(f"market[{i}] {err}")
            continue

        def _float_or_none(x: Any) -> float | None:
            if x is None:
                return None
            try:
                return float(x)
            except (TypeError, ValueError):
                return None

        bids.append(
            TypedBid(
                agent_id=str(agent_id),
                bundle_id=bundle_id,
                value=float(value),
                units=str(units).strip().lower(),
                constraints=dict(constraints),
                travel_time_estimate=_float_or_none(travel_time_estimate),
                queue_delay_estimate=_float_or_none(queue_delay_estimate),
                risk_penalty=_float_or_none(risk_penalty),
                fairness_penalty=_float_or_none(fairness_penalty),
            )
        )
    return bids, errors


def _expected_bid_from_digest(
    digest: dict[str, Any],
    agent_id: str,
    bundle_id: str,
) -> float:
    """
    Compute expected bid value from digest (travel proxy + queue proxy).
    Used to reject bids that are inconsistent with observable state.
    """
    per_agent = digest.get("per_agent") or []
    per_device = digest.get("per_device") or []
    device_zone = digest.get("device_zone") or {}
    agent_zone = ""
    for p in per_agent:
        if isinstance(p, dict) and p.get("agent_id") == agent_id:
            agent_zone = (p.get("zone") or "").strip()
            break
    if ":" in bundle_id:
        dev_id, _work = bundle_id.split(":", 1)
        device_zone_id = device_zone.get(dev_id, "")
        travel = 0.0 if (agent_zone and device_zone_id and agent_zone == device_zone_id) else 1.0
    else:
        travel = 1.0
    queue_proxy = 0.0
    for d in per_device:
        if not isinstance(d, dict):
            continue
        dev_id = str(d.get("device_id") or "")
        if bundle_id.startswith(dev_id + ":"):
            queue_proxy = float(d.get("queue_len", 0) or 0) * 0.1
            break
    return travel + queue_proxy


def _reject_inconsistent_bids(
    bids: list[TypedBid],
    digest: dict[str, Any],
    tolerance: float,
) -> tuple[list[TypedBid], list[str]]:
    """
    Drop bids whose value is inconsistent with recomputed expected range
    (travel + queue + risk + fairness) beyond tolerance.
    """
    kept: list[TypedBid] = []
    errors: list[str] = []
    for b in bids:
        base = _expected_bid_from_digest(digest, b.agent_id, b.bundle_id)
        risk = b.risk_penalty if b.risk_penalty is not None else 0.0
        fair = b.fairness_penalty if b.fairness_penalty is not None else 0.0
        travel_b = b.travel_time_estimate if b.travel_time_estimate is not None else None
        queue_b = b.queue_delay_estimate if b.queue_delay_estimate is not None else None
        if travel_b is not None and queue_b is not None:
            expected = travel_b + queue_b + risk + fair
        else:
            expected = base + risk + fair
        if abs(b.value - expected) > tolerance:
            errors.append(f"bid {b.agent_id} {b.bundle_id} value {b.value} outside tolerance of expected {expected}")
            continue
        kept.append(b)
    return kept, errors


def _assignments_to_actions(
    assignments: list[tuple[str, str, str, int]],
    obs: dict[str, Any],
    agent_ids: list[str],
    zone_ids: list[str],
    device_ids: list[str],
    device_zone: dict[str, str],
    policy: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Deterministic dispatcher: assignments -> action_dict (MOVE / START_RUN / NOOP)."""
    out: dict[str, dict[str, Any]] = {a: {"action_index": ACTION_NOOP, "action_type": "NOOP"} for a in agent_ids}
    layout = (policy or {}).get("zone_layout") or {}
    adjacency = build_adjacency_set(layout.get("graph_edges") or [])
    assign_by_agent: dict[str, tuple[str, str, str]] = {}
    for agent_id, work_id, device_id, _ in assignments:
        assign_by_agent[agent_id] = (
            work_id,
            device_id,
            device_zone.get(device_id, ""),
        )

    for agent_id in agent_ids:
        o = obs.get(agent_id) or {}
        if log_frozen(o):
            continue
        my_zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""
        if agent_id not in assign_by_agent:
            goal = zone_ids[0] if zone_ids else my_zone
            qbd = get_queue_by_device(o)
            for idx, dev_id in enumerate(device_ids):
                if idx < len(qbd) and (qbd[idx].get("queue_len") or 0) > 0:
                    goal = device_zone.get(dev_id, goal)
                    break
            if my_zone != goal:
                next_z = _bfs_next_zone(my_zone, goal, adjacency)
                if next_z:
                    out[agent_id] = {
                        "action_index": ACTION_MOVE,
                        "action_type": "MOVE",
                        "args": {"from_zone": my_zone, "to_zone": next_z},
                    }
            continue
        work_id, device_id, task_zone = assign_by_agent[agent_id]
        if my_zone == task_zone:
            out[agent_id] = {
                "action_index": ACTION_START_RUN,
                "action_type": "START_RUN",
                "args": {"device_id": device_id, "work_id": work_id},
            }
        else:
            next_z = _bfs_next_zone(my_zone, task_zone, adjacency)
            if next_z:
                out[agent_id] = {
                    "action_index": ACTION_MOVE,
                    "action_type": "MOVE",
                    "args": {"from_zone": my_zone, "to_zone": next_z},
                }
    return out


class DeterministicBidBackend:
    """
    Deterministic backend: market[] bids with typed decomposition for recompute
    validation. Optional inconsistent_bid for tests (value != sum).
    """

    DEFAULT_BACKEND_ID = "deterministic_bid"

    def __init__(
        self,
        seed: int = 0,
        backend_id: str | None = None,
        *,
        inconsistent_bid: bool = False,
    ) -> None:
        self._seed = seed
        self._backend_id = (backend_id or self.DEFAULT_BACKEND_ID).strip() or self.DEFAULT_BACKEND_ID
        self._inconsistent_bid = inconsistent_bid

    def reset(self, seed: int) -> None:
        self._seed = seed

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        step_id: int,
        method_id: str,
    ) -> dict[str, Any]:
        """Proposal with market[] bids; bid value = sum of decomposition or forced inconsistent."""
        per_agent = state_digest.get("per_agent") or []
        per_device = state_digest.get("per_device") or []
        device_zone = state_digest.get("device_zone") or {}
        market: list[dict[str, Any]] = []
        for p in per_agent:
            if not isinstance(p, dict):
                continue
            agent_id = p.get("agent_id")
            zone = (p.get("zone") or "").strip()
            for d in per_device:
                if not isinstance(d, dict):
                    continue
                dev_id = d.get("device_id") or ""
                queue_head = str(d.get("queue_head") or "").strip()
                if not dev_id or not queue_head:
                    continue
                z = device_zone.get(dev_id, "")
                prio = 2 if "STAT" in queue_head.upper() else (1 if "URGENT" in queue_head.upper() else 0)
                travel = 0.0 if (zone and z and zone == z) else 1.0
                queue_proxy = float(d.get("queue_len", 0) or 0) * 0.1
                risk_penalty = 0.0
                fairness_penalty = max(0.0, 2.0 - prio * 0.5)
                if self._inconsistent_bid:
                    value = 100.0
                    bid_payload = {
                        "value": value,
                        "units": "cost",
                        "travel_time_estimate": 1.0,
                        "queue_delay_estimate": 1.0,
                        "risk_penalty": 0.0,
                        "fairness_penalty": 0.0,
                    }
                else:
                    value = travel + queue_proxy + risk_penalty + fairness_penalty
                    bid_payload = {
                        "value": value,
                        "units": "cost",
                        "travel_time_estimate": travel,
                        "queue_delay_estimate": queue_proxy,
                        "risk_penalty": risk_penalty,
                        "fairness_penalty": fairness_penalty,
                    }
                market.append(
                    {
                        "agent_id": agent_id,
                        "bid": bid_payload,
                        "bundle": {"device_id": dev_id, "work_id": queue_head},
                        "units": "cost",
                        "constraints": {},
                    }
                )
        meta = {"backend_id": self._backend_id, "model_id": "n/a", "latency_ms": 0.0}
        try:
            from labtrust_gym.baselines.llm.llm_tracer import record_deterministic_coord_span

            record_deterministic_coord_span("coord_bid", self._backend_id)
        except Exception as e:
            _LOG.debug("Tracing coord_bid span failed: %s", e)
        return {
            "proposal_id": f"auction-det-{self._seed}-{step_id}",
            "step_id": step_id,
            "method_id": method_id,
            "horizon_steps": 1,
            "per_agent": [],
            "comms": [],
            "market": market,
            "meta": meta,
        }


class LLMAuctionBidder(CoordinationMethod):
    """
    LLM produces typed bids only (market[] in CoordinationProposal). Deterministic
    auction clears; dispatcher produces actions. Strict bid validation. Metrics:
    bid_skew, gini_work_distribution, collusion_suspected_proxy.

    Latency: one proposal generation per step (backend-dependent). Fallback: on
    backend failure, safe_fallback profile returns NOOP for all agents; otherwise
    raises. Same seed yields deterministic bids and assignments.
    """

    def __init__(
        self,
        bid_backend: Any,
        rbac_policy: dict[str, Any],
        *,
        policy_summary: dict[str, Any] | None = None,
        method_id_override: str | None = None,
        defense_profile: str | None = None,
    ) -> None:
        self._backend = bid_backend
        self._rbac_policy = rbac_policy
        self._policy_summary = policy_summary or {}
        self._method_id_override = method_id_override
        self._defense_profile = defense_profile or ""
        self._seed = 0
        self._scale_config: dict[str, Any] = {}
        self._last_metrics: dict[str, Any] = {}
        self._last_validation_errors: list[str] = []
        self._last_proposal: dict[str, Any] | None = None
        self._last_meta: dict[str, Any] | None = None

    @property
    def method_id(self) -> str:
        return self._method_id_override or "llm_auction_bidder"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._policy_summary = (policy or {}).get("policy_summary") or policy or {}
        self._scale_config = scale_config or {}
        self._seed = seed
        reset_fn = getattr(self._backend, "reset", None)
        if callable(reset_fn):
            reset_fn(seed)

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agent_ids = sorted(obs.keys())
        policy = self._policy_summary
        obs_sample = next(iter(obs.values())) if obs else None
        zone_ids, device_ids, device_zone = extract_zone_and_device_ids(policy, obs_sample=obs_sample)
        if not zone_ids and obs:
            zone_ids = ["Z_SORTING_LANES"]
        out = {a: {"action_index": ACTION_NOOP, "action_type": "NOOP"} for a in agent_ids}

        work_items = _build_work_items(obs, device_ids, device_zone)
        gen = getattr(self._backend, "generate_proposal", None)
        if not callable(gen):
            self._last_metrics = {}
            return out
        digest = build_state_digest(obs, infos or {}, t, policy)
        digest["device_zone"] = device_zone
        protocol = self._scale_config.get("coord_auction_protocol") or os.environ.get(
            "COORD_AUCTION_PROTOCOL", "single_call"
        )
        safe_fallback = self._defense_profile == "safe_fallback"
        market: list[dict[str, Any]] = []

        if protocol == "round_robin":
            for agent_id in agent_ids:
                digest_single = dict(digest)
                per_agent_full = digest_single.get("per_agent") or []
                digest_single["per_agent"] = [
                    p for p in per_agent_full if isinstance(p, dict) and p.get("agent_id") == agent_id
                ]
                if not digest_single["per_agent"] and per_agent_full:
                    digest_single["per_agent"] = [
                        {**p, "agent_id": agent_id} for p in per_agent_full[:1] if isinstance(p, dict)
                    ]
                try:
                    raw_single = gen(
                        state_digest=digest_single,
                        step_id=t,
                        method_id=self.method_id,
                    )
                except Exception as e:
                    _LOG.warning("Bid generation failed for agent %s, using fallback: %s", agent_id, e)
                    if safe_fallback:
                        continue
                    raise
                if isinstance(raw_single, tuple):
                    prop_single, _ = raw_single[0], raw_single[1]
                else:
                    prop_single = raw_single
                single_market = prop_single.get("market") or []
                for m in single_market:
                    if isinstance(m, dict) and (m.get("agent_id") == agent_id or not m.get("agent_id")):
                        market.append({**m, "agent_id": m.get("agent_id") or agent_id})
                    elif isinstance(m, dict):
                        market.append(m)
            proposal = {
                "proposal_id": f"round_robin_{t}",
                "step_id": t,
                "method_id": self.method_id,
                "per_agent": [],
                "comms": [],
                "market": market,
                "meta": {},
            }
            meta = {}
        else:
            try:
                raw = gen(
                    state_digest=digest,
                    step_id=t,
                    method_id=self.method_id,
                )
            except Exception as e:
                _LOG.warning("Proposal generation failed, using fallback: %s", e)
                if safe_fallback:
                    self._last_metrics = {}
                    return out
                raise
            if isinstance(raw, tuple):
                proposal, meta = raw[0], raw[1]
            else:
                proposal = raw
                meta = proposal.get("meta") or {}
            market = proposal.get("market") or []

        self._last_proposal = proposal
        self._last_meta = meta
        typed_bids, val_errors = _proposal_market_to_typed_bids(market, set(agent_ids))
        self._last_validation_errors = list(val_errors)
        tolerance = self._scale_config.get("bid_consistency_tolerance")
        if tolerance is not None:
            try:
                tol = float(tolerance)
                typed_bids, consistency_errors = _reject_inconsistent_bids(typed_bids, digest, tol)
                self._last_validation_errors.extend(consistency_errors)
            except (TypeError, ValueError):
                pass
        rng = random.Random(self._seed + t)
        assignments, bids_used, metrics = clear_auction(
            work_items,
            typed_bids,
            rng,
            max_assignments=max(len(agent_ids) * 2, 1),
        )
        self._last_metrics = dict(metrics)
        if self._scale_config.get("injection_id") in (
            "INJ-COLLUSION-001",
            "INJ-BID-SPOOF-001",
        ):
            self._last_metrics["injection_active"] = True
        return _assignments_to_actions(
            assignments,
            obs,
            agent_ids,
            zone_ids,
            device_ids,
            device_zone,
            policy,
        )

    def combine_submissions(
        self,
        submissions: dict[str, dict[str, Any]],
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        """
        Combine per-agent bid submissions into joint action. Each submission is
        one bid: {bid, bundle, units?, constraints?} (same shape as market[] entry).
        Builds market from submissions, runs typed bid validation, clear_auction,
        then deterministic dispatcher.
        """
        agent_ids = sorted(obs.keys()) if obs else sorted(submissions.keys())
        policy = self._policy_summary
        obs_sample = next(iter(obs.values())) if obs else None
        zone_ids, device_ids, device_zone = extract_zone_and_device_ids(policy, obs_sample=obs_sample)
        if not zone_ids and obs:
            zone_ids = ["Z_SORTING_LANES"]

        market: list[dict[str, Any]] = [
            {"agent_id": aid, **sub} for aid, sub in submissions.items() if sub and isinstance(sub, dict)
        ]
        typed_bids, _ = _proposal_market_to_typed_bids(market, set(agent_ids))
        work_items = _build_work_items(obs, device_ids, device_zone)
        rng = random.Random(self._seed + t)
        assignments, _, _ = clear_auction(
            work_items,
            typed_bids,
            rng,
            max_assignments=max(len(agent_ids) * 2, 1),
        )
        return _assignments_to_actions(
            assignments,
            obs,
            agent_ids,
            zone_ids,
            device_ids,
            device_zone,
            policy,
        )

    def get_auction_metrics(self) -> dict[str, Any]:
        """bid_skew, gini_work_distribution, collusion_suspected_proxy, validation_errors."""
        m = dict(self._last_metrics)
        m["validation_errors"] = list(self._last_validation_errors)
        return m

    def get_llm_metrics(self) -> dict[str, Any]:
        """Return metrics for coordination+LLM: tokens, latency, backend_id, model_id, estimated_cost_usd."""
        meta = self._last_meta or {}
        return {
            "tokens_in": meta.get("tokens_in", 0),
            "tokens_out": meta.get("tokens_out", 0),
            "latency_ms": meta.get("latency_ms"),
            "estimated_cost_usd": meta.get("estimated_cost_usd"),
            "backend_id": meta.get("backend_id"),
            "model_id": meta.get("model_id"),
        }
