"""
Deterministic LLM fault model wrapper for coordination paths (proposal / bid).

Wraps backends that offer generate_proposal(state_digest, ...). On trigger,
returns minimal valid proposal (all NOOP / empty market) and records metrics.
Key: (seed, step_id, method_id, input_digest) for reproducibility.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any

from labtrust_gym.baselines.llm.fault_model import (
    RC_LLM_INVALID_OUTPUT,
    _should_inject_fault,
)


def _coord_input_digest(
    state_digest: dict[str, Any],
    step_id: int,
    method_id: str,
    allowed_actions: list[str] | None = None,
) -> str:
    """Canonical SHA-256 of proposal inputs for deterministic fault keying."""
    payload = {
        "state_digest": state_digest,
        "step_id": step_id,
        "method_id": method_id,
        "allowed_actions": allowed_actions or [],
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _minimal_proposal(
    state_digest: dict[str, Any],
    step_id: int,
    method_id: str,
    seed: int,
) -> dict[str, Any]:
    """Minimal valid CoordinationProposal: per_agent all NOOP, market empty."""
    per_agent = state_digest.get("per_agent") or []
    agent_ids = [p.get("agent_id") for p in per_agent if isinstance(p, dict)]
    if not agent_ids:
        agent_ids = ["ops_0"]
    return {
        "proposal_id": f"fault-{seed}-{step_id}",
        "step_id": step_id,
        "method_id": method_id,
        "horizon_steps": 1,
        "per_agent": [
            {"agent_id": aid, "action_type": "NOOP", "args": {}}
            for aid in agent_ids
        ],
        "comms": [],
        "market": [],
        "meta": {"backend_id": "llm_fault_model_coord"},
    }


class LLMFaultModelCoordWrapper:
    """
    Wraps a proposal or bid backend (generate_proposal) and injects
    deterministic faults. On fault: returns (minimal_proposal, meta) and
    records fault_injected_count / fallback_count.
    """

    def __init__(
        self,
        inner: Any,
        config: dict[str, Any],
        seed: int = 0,
        method_id: str = "",
    ) -> None:
        self._inner = inner
        self._config = config
        self._seed = seed
        self._method_id = method_id
        self._fault_injected_count = 0
        self._fallback_count = 0

    def reset(self, seed: int) -> None:
        self._seed = seed
        self._fault_injected_count = 0
        self._fallback_count = 0
        if hasattr(self._inner, "reset"):
            self._inner.reset(seed)

    def _get_step_rng(self, step_id: int, input_digest: str) -> random.Random:
        """Per-step RNG: same seed + step + digest -> same decision."""
        seed_offset = int(self._config.get("seed_offset", 0))
        digest_part = int(input_digest[:8], 16) % (2**31)
        step_seed = (
            self._seed + seed_offset + step_id * 7919 + digest_part
        )
        return random.Random(step_seed)

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        allowed_actions: list[str] | None = None,
        step_id: int = 0,
        method_id: str | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Call inner generate_proposal; optionally inject fault. Always returns
        (proposal_dict, meta). On fault returns minimal NOOP proposal and meta
        with fault_type / reason_code.
        """
        mid = method_id if method_id is not None else self._method_id
        digest = _coord_input_digest(
            state_digest, step_id, mid, allowed_actions
        )
        faults = self._config.get("faults") or []
        step_rng = self._get_step_rng(step_id, digest)

        for fault in faults:
            if not isinstance(fault, dict):
                continue
            if _should_inject_fault(fault, step_id, step_rng):
                fault_id = fault.get("fault_id", "invalid_output")
                reason_code = fault.get(
                    "reason_code", RC_LLM_INVALID_OUTPUT
                )
                self._fault_injected_count += 1
                self._fallback_count += 1
                proposal = _minimal_proposal(
                    state_digest, step_id, mid, self._seed
                )
                meta = {
                    "backend_id": "llm_fault_model_coord",
                    "fault_type": fault_id,
                    "reason_code": reason_code,
                }
                return (proposal, meta)

        gen = getattr(self._inner, "generate_proposal", None)
        if not callable(gen):
            proposal = _minimal_proposal(
                state_digest, step_id, mid, self._seed
            )
            return (proposal, {"backend_id": "no_inner"})
        try:
            raw = gen(
                state_digest=state_digest,
                allowed_actions=allowed_actions,
                step_id=step_id,
                method_id=mid,
                **kwargs,
            )
        except TypeError:
            raw = gen(
                state_digest=state_digest,
                step_id=step_id,
                method_id=mid,
                **{k: v for k, v in kwargs.items() if k != "allowed_actions"},
            )
        if isinstance(raw, tuple):
            return (raw[0], raw[1])
        proposal = raw
        meta = proposal.get("meta") if isinstance(proposal, dict) else {}
        return (proposal, meta or {})

    def get_fault_metrics(self) -> dict[str, Any]:
        """fault_injected_count and fallback_count for rate computation."""
        return {
            "fault_injected_count": self._fault_injected_count,
            "fallback_count": self._fallback_count,
        }
