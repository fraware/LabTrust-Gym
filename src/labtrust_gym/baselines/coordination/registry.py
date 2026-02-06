"""
Coordination method factory: load registry from policy YAML and instantiate methods.
"""

from __future__ import annotations

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
    WHCARouter,
)
from labtrust_gym.baselines.coordination.kernels.scheduler_or import ORScheduler
from labtrust_gym.baselines.coordination.methods.centralized_planner import (
    CentralizedPlanner,
)
from labtrust_gym.baselines.coordination.methods.gossip_consensus import (
    GossipConsensus,
)
from labtrust_gym.baselines.coordination.methods.hierarchical_hub_rr import (
    HierarchicalHubRR,
)
from labtrust_gym.baselines.coordination.methods.llm_constrained import (
    LLMConstrained,
)
from labtrust_gym.baselines.coordination.methods.market_auction import (
    MarketAuction,
)
from labtrust_gym.baselines.coordination.methods.swarm_reactive import (
    SwarmReactive,
)


def _load_scheduler_or_policy(repo_root: Path | None) -> dict[str, Any]:
    """Load scheduler_or_policy.v0.1.yaml from repo; return dict or empty."""
    if repo_root is None:
        return {}
    path = repo_root / "policy" / "coordination" / "scheduler_or_policy.v0.1.yaml"
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
    "llm_constrained": LLMConstrained,
}


def _get_marl_ppo_if_available(**kwargs: Any) -> CoordinationMethod | None:
    from labtrust_gym.baselines.coordination.methods.marl_ppo import (
        make_marl_ppo_if_available,
    )

    return make_marl_ppo_if_available(**kwargs)


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
    **kwargs: Any,
) -> CoordinationMethod:
    """
    Instantiate a coordination method by method_id.
    Loads default_params from policy/coordination/coordination_methods.v0.1.yaml when
    repo_root is set; kwargs and explicit args override.
    """
    params: dict[str, Any] = {}
    if repo_root is not None:
        try:
            from labtrust_gym.policy.coordination import load_coordination_methods

            reg_path = Path(repo_root) / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
            if reg_path.exists():
                registry = load_coordination_methods(reg_path)
                entry = registry.get(method_id)
                if entry and isinstance(entry.get("default_params"), dict):
                    params = dict(entry["default_params"])
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

    if method_id == "marl_ppo":
        inst = _get_marl_ppo_if_available(model_path=params.get("model_path"))
        if inst is None:
            raise ImportError(
                "marl_ppo requires stable-baselines3 and gymnasium. Install with: pip install labtrust-gym[marl]"
            )
        return inst

    if method_id == "llm_constrained":
        if llm_agent is None:
            raise ValueError("llm_constrained requires llm_agent= to be passed")
        return LLMConstrained(llm_agent=llm_agent, pz_to_engine=pz_to_engine or {})

    cls = _METHOD_CLASSES.get(method_id)
    if cls is None and method_id not in (
        "kernel_centralized_edf",
        "kernel_whca",
        "kernel_scheduler_or",
        "kernel_scheduler_or_whca",
        "kernel_auction_edf",
        "kernel_auction_whca",
        "kernel_auction_whca_shielded",
    ):
        raise ValueError(
            f"Unknown coordination method_id: {method_id}. "
            f"Known: {list(_METHOD_CLASSES.keys())}, kernel_centralized_edf, "
            f"kernel_whca, kernel_scheduler_or, kernel_scheduler_or_whca, "
            f"kernel_auction_edf, kernel_auction_whca, "
            f"kernel_auction_whca_shielded, marl_ppo"
        )
    if method_id == "kernel_centralized_edf":
        alloc: CentralizedAllocator | AuctionAllocator = CentralizedAllocator(
            compute_budget=params.get("compute_budget"),
        )
        sched: EDFScheduler | ORScheduler = EDFScheduler()
        router: TrivialRouter | WHCARouter = TrivialRouter()
        return compose_kernel(alloc, sched, router, "kernel_centralized_edf")
    if method_id == "kernel_whca":
        alloc = CentralizedAllocator(
            compute_budget=params.get("compute_budget"),
        )
        sched = EDFScheduler()
        router = WHCARouter(
            horizon=params.get("whca_horizon", 15),
        )
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
        router = WHCARouter(
            horizon=params.get("whca_horizon", 15),
        )
        return compose_kernel(alloc, sched, router, "kernel_scheduler_or_whca")
    if method_id == "kernel_auction_edf":
        alloc = AuctionAllocator(
            max_bids=params.get("compute_budget") or params.get("max_bids"),
        )
        sched = EDFScheduler()
        router = TrivialRouter()
        return compose_kernel(alloc, sched, router, "kernel_auction_edf")
    if method_id == "kernel_auction_whca":
        alloc = AuctionAllocator(
            max_bids=params.get("compute_budget") or params.get("max_bids"),
        )
        sched = EDFScheduler()
        router = WHCARouter(
            horizon=params.get("whca_horizon", 15),
        )
        return compose_kernel(alloc, sched, router, "kernel_auction_whca")
    if method_id == "kernel_auction_whca_shielded":
        from labtrust_gym.baselines.coordination.assurance import (
            wrap_with_simplex_shield,
        )

        alloc = AuctionAllocator(
            max_bids=params.get("compute_budget") or params.get("max_bids"),
        )
        sched = EDFScheduler()
        router = WHCARouter(
            horizon=params.get("whca_horizon", 15),
        )
        advanced = compose_kernel(alloc, sched, router, "kernel_auction_whca")
        return cast(CoordinationMethod, wrap_with_simplex_shield(advanced, None))
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
    return cast(CoordinationMethod, cls())
