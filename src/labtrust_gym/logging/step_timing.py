"""
Optional step timing for profiling. Enable with LABTRUST_STEP_TIMING=1.
Records time spent in core_env.step(), _collect_observations, and invariants_runtime.evaluate.
Aggregates (mean, p95) can be added to benchmark metadata. No-op when disabled.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def timed_step_method(f: F) -> F:
    """Decorator for CoreEnv.step() to record duration when LABTRUST_STEP_TIMING is set."""

    def wrapped(self: Any, event: Any) -> Any:
        if not _enabled():
            return f(self, event)
        t0 = time.perf_counter()
        try:
            return f(self, event)
        finally:
            record_step_ms((time.perf_counter() - t0) * 1000)

    return wrapped  # type: ignore[return-value]


_step_ms: list[float] = []
_obs_ms: list[float] = []
_invariant_ms: list[float] = []


def _enabled() -> bool:
    return os.environ.get("LABTRUST_STEP_TIMING", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def is_enabled() -> bool:
    """Public check for whether step timing is enabled (for callers that need to avoid overhead)."""
    return _enabled()


def record_step_ms(ms: float) -> None:
    if _enabled():
        _step_ms.append(ms)


def record_obs_ms(ms: float) -> None:
    if _enabled():
        _obs_ms.append(ms)


def record_invariant_ms(ms: float) -> None:
    if _enabled():
        _invariant_ms.append(ms)


def get_aggregates() -> dict[str, Any]:
    """Return mean and p95 (ms) for step, obs, invariant. Empty if disabled or no data."""
    if not _enabled():
        return {}

    def _agg(name: str, values: list[float]) -> dict[str, float]:
        if not values:
            return {}
        s = sorted(values)
        mean = sum(s) / len(s)
        p95_idx = int(len(s) * 0.95) if len(s) > 0 else 0
        p95 = s[min(p95_idx, len(s) - 1)] if s else 0.0
        return {f"{name}_ms_mean": round(mean, 3), f"{name}_ms_p95": round(p95, 3)}

    out: dict[str, Any] = {}
    out.update(_agg("step", _step_ms))
    out.update(_agg("obs", _obs_ms))
    out.update(_agg("invariant", _invariant_ms))
    return out


def clear() -> None:
    del _step_ms[:]
    del _obs_ms[:]
    del _invariant_ms[:]
