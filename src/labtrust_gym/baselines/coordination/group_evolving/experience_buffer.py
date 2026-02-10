"""
Experience buffer: collect (state_digest, action, reward, violations, blocked_reason_code)
and summarize into small experience messages. Deterministic given seed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class ExperienceEntry:
    """Single step experience for one agent."""

    agent_id: str
    step: int
    zone_id: str
    action_type: str
    reward: float
    violations_count: int
    blocked_reason_code: str | None

    def to_summary_dict(self) -> dict[str, Any]:
        """Small dict for message payload."""
        return {
            "a": self.agent_id,
            "s": self.step,
            "z": self.zone_id,
            "act": self.action_type,
            "r": round(self.reward, 4),
            "v": self.violations_count,
            "b": self.blocked_reason_code,
        }


class ExperienceBuffer:
    """
    In-episode or cross-episode buffer; clear on reset for CI-safe deterministic variant.
    Summarize produces deterministic output given seed (sort, cap, hash).
    """

    def __init__(self, max_entries: int = 2000) -> None:
        self._max_entries = max_entries
        self._entries: list[ExperienceEntry] = []

    def append(
        self,
        agent_id: str,
        step: int,
        zone_id: str,
        action_type: str,
        reward: float,
        violations_count: int,
        blocked_reason_code: str | None,
    ) -> None:
        if len(self._entries) < self._max_entries:
            self._entries.append(
                ExperienceEntry(
                    agent_id=agent_id,
                    step=step,
                    zone_id=zone_id,
                    action_type=action_type,
                    reward=reward,
                    violations_count=violations_count,
                    blocked_reason_code=blocked_reason_code,
                )
            )

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def summarize(
        self,
        seed: int,
        max_items: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Deterministic summary: sort by (step, agent_id, zone_id), take first max_items,
        return list of to_summary_dict(). Same seed + same buffer -> same output.
        """
        if not self._entries:
            return []
        # Stable sort for determinism
        ordered = sorted(
            self._entries,
            key=(lambda e: (e.step, e.agent_id, e.zone_id)),
        )
        capped = ordered[:max_items]
        return [e.to_summary_dict() for e in capped]

    def digest_hash(self, seed: int) -> str:
        """Deterministic digest of buffer contents for checkpoint/artifact."""
        summaries = self.summarize(seed=seed, max_items=len(self._entries))
        blob = json.dumps(summaries, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]
