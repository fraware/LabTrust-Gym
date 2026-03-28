"""
Orchestrator configuration: run dir, chosen method, fallback baseline, policy root,
network allowance, and human override token for governance.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class OrchestratorConfig:
    """
    Configuration for live orchestrator runs. Used by LiveOrchestrator to resolve
    method, fallback, and defense behavior.
    """

    run_dir: Path
    """Output directory for this run (results, summary, receipts, evidence bundle)."""

    chosen_method_id: str
    """Coordination method to run (from COORDINATION_DECISION or --method)."""

    policy_root: Path
    """Policy root for scale config, RBAC, enforcement, memory policy."""

    fallback_baseline_method_id: str | None = None
    """Safe baseline method when defense triggers (e.g. kernel_centralized_edf or llm_central_planner_with_safe_fallback)."""

    allow_network: bool = False
    """Allow network for llm_live backends (openai_live, ollama_live, prime_intellect_live, ...)."""

    human_override_token: str | None = None
    """Token required to resume after kill_switch/freeze. Set via env or policy."""

    defense_enabled: bool = True
    """Apply defense controller (attack/invariant -> containment, fallback, override)."""

    scale_id: str = "small_smoke"
    """Scale config id for this run."""

    injection_id: str | None = None
    """Optional risk injection id (e.g. for red-team run). None = baseline."""

    num_episodes: int = 1
    """Number of episodes to run."""

    base_seed: int = 42
    """Base seed for reproducibility."""

    llm_backend: str | None = None
    """LLM backend: deterministic, openai_live, ollama_live, prime_intellect_live, ... None => deterministic when no LLM in method."""

    llm_model: str | None = None
    """Optional model id for live backend."""

    extra: dict[str, Any] | None = None
    """Extra options for runner (e.g. log_path, partner_id)."""
