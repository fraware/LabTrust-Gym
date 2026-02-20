"""
Coordination method factory: load registry from policy and instantiate methods.

Reads the coordination method registry from policy YAML and builds the
requested method (e.g. centralized_planner, llm_auction_bidder). External
packages can add methods via register_coordination_method() or the
labtrust_gym.coordination_methods entry point without editing this file.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from labtrust_gym.baselines.coordination.allocation.auction import (
    AuctionAllocator,
)
from labtrust_gym.baselines.coordination.compose import compose_kernel
from labtrust_gym.baselines.coordination.hierarchical import HierarchicalHubLocal
from labtrust_gym.baselines.coordination.interface import CoordinationMethod
from labtrust_gym.baselines.coordination.kernel_components import (
    CentralizedAllocator,
    EDFScheduler,
    TrivialRouter,
)
from labtrust_gym.baselines.coordination.kernels.scheduler_or import ORScheduler
from labtrust_gym.baselines.coordination.methods.centralized_planner import (
    CentralizedPlanner,
)
from labtrust_gym.baselines.coordination.methods.consensus_paxos_lite import (
    ConsensusPaxosLite,
)
from labtrust_gym.baselines.coordination.methods.gossip_consensus import (
    GossipConsensus,
)
from labtrust_gym.baselines.coordination.methods.hierarchical_hub_rr import (
    HierarchicalHubRR,
)
from labtrust_gym.baselines.coordination.methods.llm_auction_bidder import (
    DeterministicBidBackend,
    LLMAuctionBidder,
)
from labtrust_gym.baselines.coordination.methods.llm_central_planner import (
    DeterministicProposalBackend,
    LLMCentralPlanner,
)
from labtrust_gym.baselines.coordination.methods.llm_central_planner_agentic import (
    DeterministicAgenticProposalBackend,
    LLMCentralPlannerAgentic,
)
from labtrust_gym.baselines.coordination.methods.llm_central_planner_debate import (
    LLMCentralPlannerDebate,
)
from labtrust_gym.baselines.coordination.methods.llm_constrained import (
    LLMConstrained,
)
from labtrust_gym.baselines.coordination.methods.llm_gossip_summarizer import (
    LLMGossipSummarizer,
)
from labtrust_gym.baselines.coordination.methods.llm_hierarchical_allocator import (
    DeterministicAssignmentsBackend,
    LLMHierarchicalAllocator,
)
from labtrust_gym.baselines.coordination.methods.llm_local_decider_signed_bus import (
    DeterministicLocalProposalBackend,
    LLMLocalDeciderSignedBus,
)
from labtrust_gym.baselines.coordination.methods.llm_repair_over_kernel_whca import (
    DeterministicRepairBackend,
    LLMRepairOverKernelWHCA,
)
from labtrust_gym.baselines.coordination.methods.market_auction import (
    MarketAuction,
)
from labtrust_gym.baselines.coordination.methods.swarm_reactive import (
    SwarmReactive,
)
from labtrust_gym.baselines.coordination.methods.swarm_stigmergy_priority import (
    SwarmStigmergyPriority,
)
from labtrust_gym.baselines.coordination.ripple_effect import (
    MESSAGE_TYPE_RIPPLE_INTENT,
    RippleEffectMethod,
)
from labtrust_gym.baselines.coordination.routing.mapf_backends import make_router
from labtrust_gym.config import policy_path


def _load_scheduler_or_policy(repo_root: Path | None) -> dict[str, Any]:
    """Load scheduler_or_policy.v0.1.yaml from repo; return dict or empty."""
    if repo_root is None:
        return {}
    path = policy_path(repo_root, "coordination", "scheduler_or_policy.v0.1.yaml")
    if not path.exists():
        return {}
    try:
        import yaml

        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


_METHOD_CLASSES: dict[str, type] = {
    "centralized_planner": CentralizedPlanner,
    "hierarchical_hub_rr": HierarchicalHubRR,
    "hierarchical_hub_local": HierarchicalHubLocal,
    "market_auction": MarketAuction,
    "gossip_consensus": GossipConsensus,
    "swarm_reactive": SwarmReactive,
    "consensus_paxos_lite": ConsensusPaxosLite,
    "swarm_stigmergy_priority": SwarmStigmergyPriority,
    "llm_constrained": LLMConstrained,
}

# Registry for coordination method factories (method_id -> factory).
# Built-in methods are registered in _register_builtin_coordination_methods().
# External packages can call register_coordination_method() or use entry_points.
# Contract: see docs/extension_development.md (Coordination method factory contract).
CoordinationMethodFactory = Callable[
    [
        dict[str, Any],
        Path | None,
        dict[str, Any] | None,
        dict[str, Any],
    ],
    CoordinationMethod,
]
_COORDINATION_FACTORIES: dict[str, CoordinationMethodFactory] = {}


def register_coordination_method(
    method_id: str,
    factory: CoordinationMethodFactory,
) -> None:
    """Register a coordination method factory. Overwrites if present."""
    _COORDINATION_FACTORIES[method_id] = factory


def list_coordination_methods() -> list[str]:
    """Return registered coordination method IDs."""
    return sorted(_COORDINATION_FACTORIES.keys())


def _build_builtin(
    method_id: str,
    policy: dict[str, Any],
    repo_root: Path | None,
    scale_config: dict[str, Any] | None,
    params: dict[str, Any],
) -> CoordinationMethod:
    """Instantiate a built-in coordination method. Used by the registry."""

    if method_id == "llm_central_planner":
        from labtrust_gym.engine.rbac import get_allowed_actions
        from labtrust_gym.engine.rbac import load_rbac_policy as load_rbac

        backend = params.get("proposal_backend")
        if backend is None and repo_root is not None:
            seed = int((scale_config or {}).get("seed", 0))
            backend = DeterministicProposalBackend(
                seed=seed,
                default_action_type="NOOP",
            )
        if backend is None:
            raise ValueError(
                "llm_central_planner requires proposal_backend= or repo_root "
                "for deterministic backend"
            )
        rbac_path = (
            policy_path(repo_root, "rbac", "rbac_policy.v0.1.yaml") if repo_root else None
        )
        rbac_policy = load_rbac(rbac_path) if rbac_path and rbac_path.exists() else {}
        pz_to_engine_map = params.get("pz_to_engine") or {}
        first_engine = (
            next(iter(pz_to_engine_map.values()), None)
            if pz_to_engine_map
            else None
        )
        allowed = (
            get_allowed_actions(first_engine, rbac_policy)
            if first_engine
            else ["NOOP", "TICK", "QUEUE_RUN", "MOVE", "OPEN_DOOR", "START_RUN"]
        )
        sc = scale_config or {}
        max_repairs = int(sc.get("max_repairs", 1))
        blocked_threshold = int(sc.get("blocked_threshold", 0))
        return cast(
            CoordinationMethod,
            LLMCentralPlanner(
                proposal_backend=backend,
                rbac_policy=rbac_policy,
                allowed_actions=allowed,
                policy_summary=params.get("policy_summary") or policy,
                get_allowed_actions_fn=(
                    lambda aid: get_allowed_actions(aid, rbac_policy)
                ),
                max_repairs=max_repairs,
                blocked_threshold=blocked_threshold,
                method_id_override=params.get("method_id_override"),
                defense_profile=params.get("defense_profile"),
            ),
        )

    if method_id == "llm_central_planner_debate":
        from labtrust_gym.engine.rbac import get_allowed_actions
        from labtrust_gym.engine.rbac import load_rbac_policy as load_rbac

        sc = scale_config or {}
        seed = int(sc.get("seed", 0))
        n_proposers = int(sc.get("coord_debate_proposers", 2))
        n_proposers = max(1, min(n_proposers, 5))
        backends: list[Any] = []
        if params.get("proposal_backend") is not None:
            pb = params["proposal_backend"]
            backends = [pb] if not isinstance(pb, list) else list(pb)
        else:
            for i in range(n_proposers):
                backends.append(
                    DeterministicProposalBackend(
                        seed=seed + i,
                        default_action_type="NOOP",
                    )
                )
        rbac_path = (
            policy_path(repo_root, "rbac", "rbac_policy.v0.1.yaml")
            if repo_root
            else None
        )
        rbac_policy = load_rbac(rbac_path) if rbac_path and rbac_path.exists() else {}
        pz_to_engine_map = params.get("pz_to_engine") or {}
        first_engine = (
            next(iter(pz_to_engine_map.values()), None)
            if pz_to_engine_map
            else None
        )
        allowed = (
            get_allowed_actions(first_engine, rbac_policy)
            if first_engine
            else ["NOOP", "TICK", "QUEUE_RUN", "MOVE", "OPEN_DOOR", "START_RUN"]
        )
        aggregator = str(sc.get("coord_debate_aggregator", "majority")).lower()
        return cast(
            CoordinationMethod,
            LLMCentralPlannerDebate(
                proposal_backend=backends,
                rbac_policy=rbac_policy,
                allowed_actions=allowed,
                policy_summary=params.get("policy_summary") or policy,
                get_allowed_actions_fn=(
                    lambda aid: get_allowed_actions(aid, rbac_policy)
                ),
                aggregator=aggregator,
                method_id_override=params.get("method_id_override"),
            ),
        )

    if method_id == "llm_hierarchical_allocator":
        from labtrust_gym.engine.rbac import get_allowed_actions
        from labtrust_gym.engine.rbac import load_rbac_policy as load_rbac

        backend = params.get("allocator_backend")
        if backend is None and repo_root is not None:
            seed = int((scale_config or {}).get("seed", 0))
            backend = DeterministicAssignmentsBackend(seed=seed)
        if backend is None:
            raise ValueError(
                "llm_hierarchical_allocator requires allocator_backend= or repo_root "
                "for deterministic backend"
            )
        rbac_path = (
            policy_path(repo_root, "rbac", "rbac_policy.v0.1.yaml") if repo_root else None
        )
        rbac_policy = load_rbac(rbac_path) if rbac_path and rbac_path.exists() else {}
        pz_to_engine_map = params.get("pz_to_engine") or {}
        first_engine = (
            next(iter(pz_to_engine_map.values()), None)
            if pz_to_engine_map
            else None
        )
        allowed = (
            get_allowed_actions(first_engine, rbac_policy)
            if first_engine
            else ["NOOP", "TICK", "QUEUE_RUN", "MOVE", "OPEN_DOOR", "START_RUN"]
        )
        local_strategy = (params.get("local_strategy") or "edf").lower()
        if local_strategy not in ("greedy", "edf", "whca"):
            local_strategy = "edf"
        return cast(
            CoordinationMethod,
            LLMHierarchicalAllocator(
                allocator_backend=backend,
                rbac_policy=rbac_policy,
                allowed_actions=allowed,
                policy_summary=params.get("policy_summary") or policy,
                get_allowed_actions_fn=(
                    lambda aid: get_allowed_actions(aid, rbac_policy)
                ),
                local_strategy=local_strategy,
                use_whca=bool(params.get("use_whca", False)),
                whca_horizon=int(params.get("whca_horizon", 10)),
                method_id_override=params.get("method_id_override"),
                defense_profile=params.get("defense_profile"),
            ),
        )

    if method_id == "llm_central_planner_agentic":
        from labtrust_gym.engine.rbac import get_allowed_actions
        from labtrust_gym.engine.rbac import load_rbac_policy as load_rbac

        backend = params.get("proposal_backend")
        if backend is None and repo_root is not None:
            seed = int((scale_config or {}).get("seed", 0))
            backend = DeterministicAgenticProposalBackend(seed=seed)
        if backend is None:
            raise ValueError(
                "llm_central_planner_agentic requires proposal_backend= or repo_root"
            )
        rbac_path = (
            policy_path(repo_root, "rbac", "rbac_policy.v0.1.yaml")
            if repo_root
            else None
        )
        rbac_policy = load_rbac(rbac_path) if rbac_path and rbac_path.exists() else {}
        pz_to_engine_map = params.get("pz_to_engine") or {}
        first_engine = (
            next(iter(pz_to_engine_map.values()), None)
            if pz_to_engine_map
            else None
        )
        allowed = (
            get_allowed_actions(first_engine, rbac_policy)
            if first_engine
            else ["NOOP", "TICK", "QUEUE_RUN", "MOVE", "OPEN_DOOR", "START_RUN"]
        )
        sc = scale_config or {}
        max_rounds = int(sc.get("coord_agentic_max_rounds", 5))
        return cast(
            CoordinationMethod,
            LLMCentralPlannerAgentic(
                proposal_backend=backend,
                rbac_policy=rbac_policy,
                allowed_actions=allowed,
                policy_summary=params.get("policy_summary") or policy,
                get_allowed_actions_fn=(
                    lambda aid: get_allowed_actions(aid, rbac_policy)
                ),
                max_tool_rounds=max_rounds,
                method_id_override=params.get("method_id_override"),
            ),
        )

    if method_id == "llm_auction_bidder":
        from labtrust_gym.engine.rbac import load_rbac_policy as load_rbac

        backend = params.get("bid_backend")
        if backend is None and repo_root is not None:
            seed = int((scale_config or {}).get("seed", 0))
            backend = DeterministicBidBackend(seed=seed)
        if backend is None:
            raise ValueError(
                "llm_auction_bidder requires bid_backend= or repo_root "
                "for deterministic backend"
            )
        rbac_path = (
            policy_path(repo_root, "rbac", "rbac_policy.v0.1.yaml") if repo_root else None
        )
        rbac_policy = load_rbac(rbac_path) if rbac_path and rbac_path.exists() else {}
        return cast(
            CoordinationMethod,
            LLMAuctionBidder(
                bid_backend=backend,
                rbac_policy=rbac_policy,
                policy_summary=params.get("policy_summary") or policy,
                method_id_override=params.get("method_id_override"),
                defense_profile=params.get("defense_profile"),
            ),
        )

    if method_id == "llm_gossip_summarizer":
        from labtrust_gym.coordination.identity import build_key_store

        pz_map = params.get("pz_to_engine") or {}
        agent_ids = sorted(set(pz_map.values())) if pz_map else ["ops_0", "runner_0"]
        seed = int((scale_config or {}).get("seed", 0))
        key_store = build_key_store(agent_ids, seed)
        if not key_store:
            raise ValueError(
                "llm_gossip_summarizer requires cryptography and non-empty "
                "pz_to_engine for key_store"
            )
        identity_policy = {
            "allowed_message_types": ["gossip_summary"],
        }
        summary_backend = params.get("summary_backend")
        return cast(
            CoordinationMethod,
            LLMGossipSummarizer(
                key_store=key_store,
                repo_root=repo_root,
                identity_policy=identity_policy,
                summary_backend=summary_backend,
            ),
        )
    if method_id == "llm_local_decider_signed_bus":
        from labtrust_gym.coordination.identity import build_key_store
        from labtrust_gym.engine.rbac import get_allowed_actions
        from labtrust_gym.engine.rbac import load_rbac_policy as load_rbac

        pz_map = params.get("pz_to_engine") or {}
        agent_ids = sorted(set(pz_map.values())) if pz_map else []
        if not agent_ids and scale_config:
            scale_agents = (scale_config or {}).get("agents")
            if isinstance(scale_agents, list):
                agent_ids = [
                    a.get("agent_id") for a in scale_agents
                    if isinstance(a, dict) and a.get("agent_id")
                ]
        if not agent_ids:
            agent_ids = ["ops_0", "runner_0"]
        seed = int((scale_config or {}).get("seed", 0))
        key_store = build_key_store(agent_ids, seed)
        if not key_store:
            raise ValueError(
                "llm_local_decider_signed_bus requires cryptography and "
                "non-empty agent set for key_store"
            )
        backend = params.get("proposal_backend")
        if backend is None:
            backend = DeterministicLocalProposalBackend(seed=seed)
        rbac_path = (
            policy_path(repo_root, "rbac", "rbac_policy.v0.1.yaml") if repo_root else None
        )
        rbac_policy = load_rbac(rbac_path) if rbac_path and rbac_path.exists() else {}
        first_engine = (
            next(iter(pz_map.values()), agent_ids[0])
            if pz_map
            else agent_ids[0]
        )
        allowed = (
            get_allowed_actions(first_engine, rbac_policy)
            if rbac_policy
            else ["NOOP", "TICK", "MOVE", "START_RUN", "QUEUE_RUN", "OPEN_DOOR"]
        )
        return cast(
            CoordinationMethod,
            LLMLocalDeciderSignedBus(
                key_store=key_store,
                proposal_backend=backend,
                identity_policy={"allowed_message_types": ["action_proposal"]},
                allowed_actions=allowed,
            ),
        )

    if method_id == "marl_ppo":
        from labtrust_gym.baselines.coordination.methods.marl_ppo import (
            make_marl_ppo_if_available,
        )

        inst = make_marl_ppo_if_available(model_path=params.get("model_path"))
        if inst is None:
            raise ImportError(
                "marl_ppo requires stable-baselines3 and gymnasium. Install with: pip install labtrust-gym[marl]"
            )
        return inst

    if method_id == "llm_constrained":
        _llm_agent = params.get("llm_agent")
        if _llm_agent is None:
            raise ValueError("llm_constrained requires llm_agent= to be passed")
        return LLMConstrained(
            llm_agent=_llm_agent,
            pz_to_engine=params.get("pz_to_engine") or {},
        )

    cls = _METHOD_CLASSES.get(method_id)
    if cls is None and method_id not in (
        "consensus_paxos_lite",
        "swarm_stigmergy_priority",
        "kernel_centralized_edf",
        "kernel_whca",
        "kernel_scheduler_or",
        "kernel_scheduler_or_whca",
        "kernel_auction_edf",
        "kernel_auction_whca",
        "kernel_auction_whca_shielded",
        "llm_central_planner",
        "llm_hierarchical_allocator",
        "llm_auction_bidder",
        "llm_gossip_summarizer",
        "llm_local_decider_signed_bus",
        "llm_repair_over_kernel_whca",
        "llm_detector_throttle_advisor",
        "marl_ppo",
        "ripple_effect",
        "group_evolving_experience_sharing",
        "group_evolving_study",
    ):
        raise ValueError(
            f"Unknown coordination method_id: {method_id}. "
            f"Known: {list(_METHOD_CLASSES.keys())}, llm_central_planner, "
            f"llm_hierarchical_allocator, llm_auction_bidder, llm_gossip_summarizer, "
            f"llm_local_decider_signed_bus, llm_repair_over_kernel_whca, "
            f"llm_detector_throttle_advisor, kernel_*, marl_ppo, ripple_effect, "
            f"group_evolving_experience_sharing, group_evolving_study, "
            f"consensus_paxos_lite, swarm_stigmergy_priority"
        )
    if method_id == "group_evolving_experience_sharing":
        from labtrust_gym.baselines.coordination.group_evolving.method import (
            ExperienceSharingDeterministic,
        )
        return cast(
            CoordinationMethod,
            ExperienceSharingDeterministic(
                share_interval=params.get("share_interval", 5),
                summary_max_items=params.get("summary_max_items", 50),
            ),
        )
    if method_id == "group_evolving_study":
        from labtrust_gym.baselines.coordination.group_evolving.method import (
            GroupEvolvingStudy,
        )
        return cast(
            CoordinationMethod,
            GroupEvolvingStudy(
                share_interval=params.get("share_interval", 5),
                summary_max_items=params.get("summary_max_items", 50),
                population_size=params.get("population_size", 4),
                top_k=params.get("top_k", 2),
                episodes_per_generation=params.get("episodes_per_generation", 2),
            ),
        )
    if method_id == "ripple_effect":
        from labtrust_gym.coordination.identity import build_key_store

        pz_map = params.get("pz_to_engine") or {}
        # Key store must use IDs that appear in obs (PZ names), so signing works.
        agent_ids = sorted(pz_map.keys()) if pz_map else []
        if not agent_ids and scale_config:
            scale_agents = (scale_config or {}).get("agents")
            if isinstance(scale_agents, list):
                agent_ids = [
                    a.get("agent_id")
                    for a in scale_agents
                    if isinstance(a, dict) and a.get("agent_id")
                ]
        if not agent_ids:
            agent_ids = ["ops_0", "runner_0"]
        seed = int((scale_config or {}).get("seed", 0))
        key_store = build_key_store(agent_ids, seed)
        if not key_store:
            raise ValueError(
                "ripple_effect requires cryptography and non-empty agent set "
                "for key_store (install [llm_openai] or cryptography)"
            )
        return cast(
            CoordinationMethod,
            RippleEffectMethod(
                key_store=key_store,
                identity_policy={
                    "allowed_message_types": [MESSAGE_TYPE_RIPPLE_INTENT],
                },
            ),
        )
    if method_id == "kernel_centralized_edf":
        alloc = CentralizedAllocator(
            compute_budget=params.get("compute_budget"),
            fairness=bool(params.get("fairness", False)),
        )
        crit_slack_ce = params.get("criticality_slack_steps")
        if isinstance(crit_slack_ce, dict):
            crit_slack_ce = {int(k): int(v) for k, v in crit_slack_ce.items()}
        else:
            crit_slack_ce = None
        preemption_sla = params.get("preemption_sla_threshold")
        if preemption_sla is not None:
            preemption_sla = int(preemption_sla)
        sched = EDFScheduler(
            deadline_slack_steps=int(params.get("deadline_slack_steps", 20)),
            criticality_slack_steps=crit_slack_ce,
            preemption_sla_threshold=preemption_sla,
            aging_steps_per_boost=int(params.get("aging_steps_per_boost", 10)),
        )
        router = TrivialRouter()
        return compose_kernel(alloc, sched, router, "kernel_centralized_edf")
    if method_id == "kernel_whca":
        alloc = CentralizedAllocator(
            compute_budget=params.get("compute_budget"),
            fairness=bool(params.get("fairness", False)),
        )
        crit_slack = params.get("criticality_slack_steps")
        if isinstance(crit_slack, dict):
            crit_slack = {int(k): int(v) for k, v in crit_slack.items()}
        else:
            crit_slack = None
        sched = EDFScheduler(
            deadline_slack_steps=int(params.get("deadline_slack_steps", 20)),
            criticality_slack_steps=crit_slack,
        )
        router_backend = (scale_config or {}).get("router_backend", "whca")
        router = make_router(router_backend, horizon=params.get("whca_horizon", 15))
        return compose_kernel(alloc, sched, router, "kernel_whca")
    if method_id == "kernel_scheduler_or":
        scheduler_policy = _load_scheduler_or_policy(repo_root)
        alloc = CentralizedAllocator(
            compute_budget=params.get("compute_budget"),
        )
        sched = ORScheduler(policy=scheduler_policy)
        router = TrivialRouter()
        return compose_kernel(alloc, sched, router, "kernel_scheduler_or")
    if method_id == "kernel_scheduler_or_whca":
        scheduler_policy = _load_scheduler_or_policy(repo_root)
        alloc = CentralizedAllocator(
            compute_budget=params.get("compute_budget"),
        )
        sched = ORScheduler(policy=scheduler_policy)
        router_backend = (scale_config or {}).get("router_backend", "whca")
        router = make_router(router_backend, horizon=params.get("whca_horizon", 15))
        return compose_kernel(alloc, sched, router, "kernel_scheduler_or_whca")
    if method_id == "kernel_auction_edf":
        alloc = AuctionAllocator(
            max_bids=params.get("compute_budget") or params.get("max_bids"),
            fairness_weight=float(params.get("fairness_weight", 0)),
        )
        crit_slack_edf = params.get("criticality_slack_steps")
        if isinstance(crit_slack_edf, dict):
            crit_slack_edf = {int(k): int(v) for k, v in crit_slack_edf.items()}
        else:
            crit_slack_edf = None
        sched = EDFScheduler(
            deadline_slack_steps=int(params.get("deadline_slack_steps", 20)),
            criticality_slack_steps=crit_slack_edf,
        )
        router = TrivialRouter()
        return compose_kernel(alloc, sched, router, "kernel_auction_edf")
    if method_id == "kernel_auction_whca":
        alloc = AuctionAllocator(
            max_bids=params.get("compute_budget") or params.get("max_bids"),
            fairness_weight=float(params.get("fairness_weight", 0)),
        )
        crit_slack = params.get("criticality_slack_steps")
        if isinstance(crit_slack, dict):
            crit_slack = {int(k): int(v) for k, v in crit_slack.items()}
        else:
            crit_slack = None
        sched = EDFScheduler(
            deadline_slack_steps=int(params.get("deadline_slack_steps", 20)),
            criticality_slack_steps=crit_slack,
        )
        router_backend = (scale_config or {}).get("router_backend", "whca")
        router = make_router(router_backend, horizon=params.get("whca_horizon", 15))
        return compose_kernel(alloc, sched, router, "kernel_auction_whca")
    if method_id == "kernel_auction_whca_shielded":
        from labtrust_gym.baselines.coordination.assurance import (
            wrap_with_simplex_shield,
        )

        alloc = AuctionAllocator(
            max_bids=params.get("compute_budget") or params.get("max_bids"),
            fairness_weight=float(params.get("fairness_weight", 0)),
        )
        crit_slack = params.get("criticality_slack_steps")
        if isinstance(crit_slack, dict):
            crit_slack = {int(k): int(v) for k, v in crit_slack.items()}
        else:
            crit_slack = None
        sched = EDFScheduler(
            deadline_slack_steps=int(params.get("deadline_slack_steps", 20)),
            criticality_slack_steps=crit_slack,
        )
        router_backend = (scale_config or {}).get("router_backend", "whca")
        router = make_router(router_backend, horizon=params.get("whca_horizon", 15))
        advanced = compose_kernel(alloc, sched, router, "kernel_auction_whca")
        return cast(CoordinationMethod, wrap_with_simplex_shield(advanced, None))
    if method_id == "llm_repair_over_kernel_whca":
        from labtrust_gym.engine.rbac import get_allowed_actions
        from labtrust_gym.engine.rbac import load_rbac_policy as load_rbac

        seed = int((scale_config or {}).get("seed", 0))
        whca_horizon = int(params.get("whca_horizon", 15))
        alloc = CentralizedAllocator(
            compute_budget=params.get("compute_budget"),
        )
        sched = EDFScheduler()
        router_backend = (scale_config or {}).get("router_backend", "whca")
        router = make_router(router_backend, horizon=whca_horizon)
        kernel = compose_kernel(alloc, sched, router, "kernel_whca")
        repair_backend = params.get("repair_backend")
        if repair_backend is None:
            repair_backend = DeterministicRepairBackend(seed=seed)
        fault_model_config = (scale_config or {}).get("fault_model_config")
        if fault_model_config and fault_model_config.get("enabled"):
            from labtrust_gym.baselines.llm.fault_model import (
                LLMFaultModelRepairWrapper,
            )

            repair_backend = LLMFaultModelRepairWrapper(
                repair_backend, fault_model_config, seed=seed
            )
        rbac_path = (
            policy_path(repo_root, "rbac", "rbac_policy.v0.1.yaml") if repo_root else None
        )
        rbac_policy = load_rbac(rbac_path) if rbac_path and rbac_path.exists() else {}
        pz_to_engine_map = params.get("pz_to_engine") or {}
        first_engine = (
            next(iter(pz_to_engine_map.values()), None)
            if pz_to_engine_map
            else None
        )
        allowed = (
            get_allowed_actions(first_engine, rbac_policy)
            if first_engine
            else ["NOOP", "TICK", "QUEUE_RUN", "MOVE", "OPEN_DOOR", "START_RUN"]
        )
        return cast(
            CoordinationMethod,
            LLMRepairOverKernelWHCA(
                kernel=kernel,
                repair_backend=repair_backend,
                allowed_actions=allowed,
            ),
        )
    if method_id == "llm_detector_throttle_advisor":
        from labtrust_gym.baselines.coordination.assurance import (
            DeterministicDetectorBackend,
            wrap_with_detector_advisor,
            wrap_with_simplex_shield,
        )

        sc = params.get("scale_config") or scale_config or {}
        seed = int(sc.get("seed", 0))
        compute_budget = params.get("compute_budget") or params.get("max_bids") or sc.get("compute_budget_node_expansions")
        alloc = AuctionAllocator(
            max_bids=compute_budget or params.get("max_bids"),
        )
        sched = EDFScheduler()
        router_backend = (scale_config or {}).get("router_backend", "whca")
        router = make_router(router_backend, horizon=params.get("whca_horizon", 15))
        advanced = compose_kernel(alloc, sched, router, "kernel_auction_whca")
        shielded = wrap_with_simplex_shield(advanced, None)
        detector_backend = params.get("detector_backend")
        if detector_backend is None:
            detector_backend = DeterministicDetectorBackend(
                seed=seed,
                latency_bound_steps=int(params.get("detector_latency_bound_steps", 5)),
            )
        return cast(
            CoordinationMethod,
            wrap_with_detector_advisor(shielded, detector_backend),
        )
    if cls is None:
        raise ValueError(f"Unknown method_id: {method_id}")
    if method_id == "centralized_planner":
        return cast(CoordinationMethod, cls(compute_budget=params.get("compute_budget")))
    if method_id == "hierarchical_hub_rr":
        return cast(CoordinationMethod, cls(message_delay_scale=params.get("message_delay_scale", 1.0)))
    if method_id == "hierarchical_hub_local":
        return cast(
            CoordinationMethod,
            cls(
                ack_deadline_steps=params.get("ack_deadline_steps", 10),
                sla_horizon=params.get("sla_horizon", 20),
            ),
        )
    if method_id == "market_auction":
        return cast(CoordinationMethod, cls(collusion=params.get("collusion", False)))
    if method_id == "gossip_consensus":
        return cast(CoordinationMethod, cls(gossip_rounds=params.get("gossip_rounds", 3)))
    if method_id == "swarm_reactive":
        return cast(CoordinationMethod, cls())
    if method_id == "consensus_paxos_lite":
        return cast(
            CoordinationMethod,
            cls(max_rounds=params.get("max_rounds", 2)),
        )
    if method_id == "swarm_stigmergy_priority":
        return cast(
            CoordinationMethod,
            cls(
                decay=params.get("pheromone_decay", 0.95),
                deposit=params.get("pheromone_deposit", 1.0),
            ),
        )
    return cast(CoordinationMethod, cls())

BUILTIN_COORDINATION_METHOD_IDS: tuple[str, ...] = (
    'centralized_planner',
    'consensus_paxos_lite',
    'gossip_consensus',
    'group_evolving_experience_sharing',
    'group_evolving_study',
    'hierarchical_hub_local',
    'hierarchical_hub_rr',
    'kernel_auction_edf',
    'kernel_auction_whca',
    'kernel_auction_whca_shielded',
    'kernel_centralized_edf',
    'kernel_scheduler_or',
    'kernel_scheduler_or_whca',
    'kernel_whca',
    'llm_auction_bidder',
    'llm_central_planner',
    'llm_central_planner_debate',
    'llm_central_planner_agentic',
    'llm_constrained',
    'llm_detector_throttle_advisor',
    'llm_gossip_summarizer',
    'llm_hierarchical_allocator',
    'llm_local_decider_signed_bus',
    'llm_repair_over_kernel_whca',
    'market_auction',
    'marl_ppo',
    'ripple_effect',
    'swarm_reactive',
    'swarm_stigmergy_priority',
)


def _register_builtin_coordination_methods() -> None:
    for mid in BUILTIN_COORDINATION_METHOD_IDS:
        def _factory(p, r, s, params, _mid=mid):
            return _build_builtin(_mid, p, r, s, params)
        register_coordination_method(mid, _factory)


_register_builtin_coordination_methods()


def make_coordination_method(
    method_id: str,
    policy: dict[str, Any],
    repo_root: Path | None = None,
    scale_config: dict[str, Any] | None = None,
    compute_budget: int | None = None,
    collusion: bool = False,
    message_delay_scale: float = 1.0,
    gossip_rounds: int = 3,
    model_path: str | None = None,
    llm_agent: Any | None = None,
    pz_to_engine: dict[str, str] | None = None,
    proposal_backend: Any | None = None,
    **kwargs: Any,
) -> CoordinationMethod:
    """
    Instantiate a coordination method by method_id.
    Loads default_params from policy/coordination/coordination_methods.v0.1.yaml when
    repo_root is set; kwargs and explicit args override.
    """
    params: dict[str, Any] = {}
    registry: dict[str, dict[str, Any]] = {}
    if repo_root is not None:
        try:
            from labtrust_gym.policy.coordination import (
                load_coordination_methods,
                resolve_method_variant,
            )

            reg_path = policy_path(repo_root, "coordination", "coordination_methods.v0.1.yaml")
            if reg_path.exists():
                registry = load_coordination_methods(reg_path)
                entry = registry.get(method_id)
                if entry and isinstance(entry.get("default_params"), dict):
                    params = dict(entry["default_params"])
                base_id, defense_profile = resolve_method_variant(method_id, registry)
                if base_id != method_id:
                    params["method_id_override"] = method_id
                    if defense_profile is not None:
                        params["defense_profile"] = defense_profile
                    base_entry = registry.get(base_id)
                    if base_entry and isinstance(base_entry.get("default_params"), dict):
                        params = {**base_entry["default_params"], **params}
                    method_id = base_id
        except Exception:
            pass
    if scale_config:
        params["scale_config"] = scale_config
    params.update(kwargs)
    if compute_budget is not None:
        params["compute_budget"] = compute_budget
    if collusion:
        params["collusion"] = collusion
    if message_delay_scale != 1.0:
        params["message_delay_scale"] = message_delay_scale
    if gossip_rounds != 3:
        params["gossip_rounds"] = gossip_rounds
    if model_path is not None:
        params["model_path"] = model_path
    if llm_agent is not None:
        params["llm_agent"] = llm_agent
    if pz_to_engine is not None:
        params["pz_to_engine"] = pz_to_engine
    if proposal_backend is not None:
        params["proposal_backend"] = proposal_backend

    # External plugins may register a factory for this method_id; use it if present.
    factory = _COORDINATION_FACTORIES.get(method_id)
    if factory is not None:
        return factory(policy, repo_root, scale_config, params)
    factory = _COORDINATION_FACTORIES.get(method_id)
    if factory is None:
        raise ValueError(
            f"Unknown coordination method_id: {method_id}. Known: {sorted(_COORDINATION_FACTORIES.keys())}"
        )
    return factory(policy, repo_root, scale_config, params)
