"""
Minimal clock advancement for simulated timing.

Supports set(t_s) and advance_to(t_s). Used by devices to complete runs
when time reaches run end_time.
"""

from __future__ import annotations

from typing import Any, Callable, List, Tuple


class Clock:
    """
    Simulation clock. now_ts is updated by advance_to(t_s).
    Optional callback for device completions when time advances.
    """

    def __init__(self) -> None:
        self._now_ts: int = 0

    @property
    def now_ts(self) -> int:
        return self._now_ts

    def set(self, t_s: int) -> None:
        """Set clock to t_s (e.g. from event)."""
        self._now_ts = int(t_s)

    def advance_to(
        self,
        t_s: int,
        completion_callback: Callable[[int], List[Tuple[str, str]]],
    ) -> List[Tuple[str, str]]:
        """
        Advance clock to t_s. Call completion_callback(now_ts) to get
        list of (device_id, run_id) that completed in (prev_now, t_s].
        Returns that list.
        """
        prev = self._now_ts
        self._now_ts = int(t_s)
        return completion_callback(self._now_ts)
