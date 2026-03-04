"""
Deterministic LLM fault model wrapper for the agent path (llm_offline).

Wraps an LLMBackend (generate(messages) -> str) and injects seeded failures
using the same config as the repair path
(policy/llm/llm_fault_model.v0.1.yaml). On trigger, returns safe NOOP
ActionProposal JSON and records metrics.
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


def _messages_digest(messages: list[dict[str, str]]) -> str:
    """Canonical SHA-256 digest of messages (same as agent._messages_digest)."""  # noqa: E501
    canonical = json.dumps(messages, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _noop_fallback_json(reason_code: str) -> str:
    """Valid ActionProposal JSON for NOOP with reason_code (fault fallback)."""
    return json.dumps(
        {
            "action_type": "NOOP",
            "args": {},
            "reason_code": reason_code,
            "token_refs": [],
            "rationale": "fault_injected",
            "confidence": 0.0,
            "safety_notes": "",
        },
        sort_keys=True,
    )


class LLMFaultModelAgentWrapper:
    """
    Wraps an LLMBackend and injects deterministic faults for the agent path.
    Uses (seed, call_index, message_digest) for reproducible injection.
    On fault: returns NOOP ActionProposal JSON and increments fault metrics.
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
        self._call_count = 0
        self._fault_injected_count = 0
        self._fallback_count = 0

    def reset(self, seed: int) -> None:
        self._seed = seed
        self._call_count = 0
        self._fault_injected_count = 0
        self._fallback_count = 0
        if hasattr(self._inner, "reset"):
            self._inner.reset(seed)

    def _get_call_rng(self, call_index: int, message_digest: str) -> random.Random:
        """Per-call RNG: same seed + call_index + digest -> same decision."""  # noqa: E501
        seed_offset = int(self._config.get("seed_offset", 0))
        digest_part = int(message_digest[:8], 16) % (2**31)
        call_seed = self._seed + seed_offset + call_index * 7919 + digest_part
        return random.Random(call_seed)

    def generate(self, messages: list[dict[str, str]]) -> str:
        """
        Call inner backend; optionally inject a fault (deterministic). On
        fault, return NOOP ActionProposal JSON with reason_code.
        """
        call_index = self._call_count
        self._call_count += 1
        digest = _messages_digest(messages)
        faults = self._config.get("faults") or []
        step_rng = self._get_call_rng(call_index, digest)

        for fault in faults:
            if not isinstance(fault, dict):
                continue
            if _should_inject_fault(fault, call_index, step_rng):
                reason_code = fault.get("reason_code", RC_LLM_INVALID_OUTPUT)
                self._fault_injected_count += 1
                self._fallback_count += 1
                return _noop_fallback_json(reason_code)

        return self._inner.generate(messages)

    def get_fault_metrics(self) -> dict[str, Any]:
        """fault_injected_count and fallback_count for rate computation."""
        return {
            "fault_injected_count": self._fault_injected_count,
            "fallback_count": self._fallback_count,
        }
