"""
Deterministic LLM fault model wrapper for llm_offline mode.

Wraps a repair backend (or proposal backend) and injects seeded failures:
invalid_output, empty_output, high_latency, inconsistent_plan. When a fault
triggers, returns safe NOOP fallback and records reason codes. Metrics:
fault_injected_count, fallback_count (exposed as rates in results).
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.coordination.repair_input import repair_input_hash
from labtrust_gym.policy.loader import load_yaml

# Reason codes (must exist in reason_code_registry)
RC_LLM_INVALID_OUTPUT = "RC_LLM_INVALID_OUTPUT"
LLM_REFUSED = "LLM_REFUSED"
RC_LLM_FAULT_INJECTED = "RC_LLM_FAULT_INJECTED"


def load_llm_fault_model(repo_root: Path | None) -> dict[str, Any]:
    """Load policy/llm/llm_fault_model.v0.1.yaml; return {} if missing or disabled."""
    if repo_root is None:
        return {}
    path = Path(repo_root) / "policy" / "llm" / "llm_fault_model.v0.1.yaml"
    if not path.is_file():
        return {}
    try:
        data = load_yaml(path)
        if not data.get("enabled", False):
            return {}
        return data
    except Exception:
        return {}


def _step_from_repair_input(repair_input: dict[str, Any]) -> int:
    """Extract step index from repair input for deterministic fault scheduling."""
    summary = repair_input.get("last_accepted_plan_summary") or {}
    return int(summary.get("step_idx", 0))


def _should_inject_fault(
    fault: dict[str, Any],
    step: int,
    step_rng: random.Random,
) -> bool:
    """True if this fault should trigger this step (seeded, deterministic)."""
    step_intervals = fault.get("step_intervals")
    if step_intervals is not None and isinstance(step_intervals, list):
        return step in step_intervals
    p = float(fault.get("probability", 0.0))
    if p <= 0:
        return False
    return step_rng.random() < p


class LLMFaultModelRepairWrapper:
    """
    Wraps a repair backend and injects deterministic faults when enabled.
    Fallback is all NOOP; records fault_injected_count and fallback_count.
    """

    def __init__(
        self,
        inner: Any,
        config: dict[str, Any],
        seed: int = 0,
    ) -> None:
        self._inner = inner
        self._config = config
        self._seed = seed
        self._fault_injected_count = 0
        self._fallback_count = 0

    def reset(self, seed: int) -> None:
        self._seed = seed
        self._fault_injected_count = 0
        self._fallback_count = 0
        if hasattr(self._inner, "reset"):
            self._inner.reset(seed)

    def _get_step_rng(self, step: int, repair_input: dict[str, Any]) -> random.Random:
        """Per-step RNG: same seed + step + input hash -> same sequence."""
        seed_offset = int(self._config.get("seed_offset", 0))
        h = repair_input_hash(repair_input)
        step_seed = (
            self._seed + seed_offset + step * 7919 + (int(h[:8], 16) % (2**31))
        )
        return random.Random(step_seed)

    def repair(
        self,
        repair_input: dict[str, Any],
        agent_ids: list[str],
    ) -> tuple[list[tuple[str, str, dict[str, Any]]], dict[str, Any]]:
        """
        Call inner repair; optionally inject a fault (deterministic). On fault,
        return all NOOP and record reason_code in meta.
        """
        step = _step_from_repair_input(repair_input)
        faults = self._config.get("faults") or []
        step_rng = self._get_step_rng(step, repair_input)

        for fault in faults:
            if not isinstance(fault, dict):
                continue
            if _should_inject_fault(fault, step, step_rng):
                fault_id = fault.get("fault_id", "invalid_output")
                reason_code = fault.get("reason_code", RC_LLM_INVALID_OUTPUT)
                self._fault_injected_count += 1
                self._fallback_count += 1
                per_agent = [(aid, "NOOP", {}) for aid in sorted(agent_ids)]
                meta = {
                    "backend_id": "llm_fault_model_wrapper",
                    "fault_type": fault_id,
                    "reason_code": reason_code,
                    "latency_ms": 0.0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                }
                if fault_id == "high_latency":
                    meta["latency_ms"] = float(
                        fault.get("simulated_latency_ms", 5000.0)
                    )
                return per_agent, meta

        per_agent, meta = self._inner.repair(repair_input, agent_ids)
        return per_agent, meta

    def get_fault_metrics(self) -> dict[str, Any]:
        """Return fault_injected_count and fallback_count for rate computation."""
        return {
            "fault_injected_count": self._fault_injected_count,
            "fallback_count": self._fallback_count,
        }
