"""
Per-agent clock model: skew_ppm and offset_ms for timing semantics and injection.
Deterministic: same seed => same skew/offset per agent.
"""

from __future__ import annotations

import random


class ClockModel:
    """
    Per-agent clock: local_time_ms = global_step * dt_ms * (1 + skew_ppm/1e6) + offset_ms.
    Used to model clock skew and to inject INJ-CLOCK-SKEW-001 (seeded).
    """

    __slots__ = ("_agent_ids", "_skew_ppm", "_offset_ms", "_rng")

    def __init__(
        self,
        agent_ids: list[str],
        skew_ppm: dict[str, float] | None = None,
        offset_ms: dict[str, float] | None = None,
        seed: int = 0,
    ) -> None:
        self._agent_ids = sorted(agent_ids)
        self._rng = random.Random(seed)
        self._skew_ppm: dict[str, float] = {}
        self._offset_ms: dict[str, float] = {}
        for aid in self._agent_ids:
            self._skew_ppm[aid] = (skew_ppm or {}).get(aid, 0.0)
            self._offset_ms[aid] = (offset_ms or {}).get(aid, 0.0)

    def reset(
        self,
        seed: int,
        skew_ppm_override: dict[str, float] | None = None,
        offset_ms_override: dict[str, float] | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        for aid in self._agent_ids:
            if skew_ppm_override is not None and aid in skew_ppm_override:
                self._skew_ppm[aid] = skew_ppm_override[aid]
            elif skew_ppm_override is None:
                pass
            else:
                self._skew_ppm[aid] = 0.0
            if offset_ms_override is not None and aid in offset_ms_override:
                self._offset_ms[aid] = offset_ms_override[aid]
            elif offset_ms_override is None:
                pass
            else:
                self._offset_ms[aid] = 0.0

    def inject_skew_from_rng(
        self,
        skew_ppm_range: float = 100.0,
        offset_ms_range: float = 50.0,
    ) -> None:
        """Set skew and offset per agent from internal RNG (deterministic)."""
        for aid in self._agent_ids:
            self._skew_ppm[aid] = (self._rng.random() * 2 - 1) * skew_ppm_range
            self._offset_ms[aid] = (self._rng.random() * 2 - 1) * offset_ms_range

    def global_step_to_ms(self, step: int, dt_ms: float = 10.0) -> float:
        """Convert global step to reference time in ms."""
        return step * dt_ms

    def agent_local_time_ms(
        self,
        agent_id: str,
        global_step: int,
        dt_ms: float = 10.0,
    ) -> float:
        """Agent's local time in ms at global_step (with skew and offset)."""
        ref_ms = global_step * dt_ms
        skew = self._skew_ppm.get(agent_id, 0.0)
        offset = self._offset_ms.get(agent_id, 0.0)
        return ref_ms * (1.0 + skew / 1e6) + offset

    def view_age_ms(
        self,
        decision_step: int,
        last_processing_step: int | None,
        dt_ms: float = 10.0,
    ) -> float:
        """
        View age at decision_step: ms since last_processing_step.
        If last_processing_step is None, return 0 or a large value (no events yet).
        """
        if last_processing_step is None:
            return 0.0
        return max(0.0, (decision_step - last_processing_step) * dt_ms)
