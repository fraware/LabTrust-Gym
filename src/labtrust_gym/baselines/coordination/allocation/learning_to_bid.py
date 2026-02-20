"""
Learning-to-bid: lightweight regressor from experience buffer.
Predict service time / success probability / QC-fail risk; bidder uses predicted cost.
Clearing stays deterministic. Optional module.
"""

from __future__ import annotations

import hashlib
from typing import Any


def _model_state_hash(state: dict[str, Any]) -> str:
    """Deterministic hash of model state for checksum."""
    parts = []
    for k in sorted(state.keys()):
        v = state[k]
        if isinstance(v, float):
            parts.append(f"{k}={v:.10f}")
        else:
            parts.append(f"{k}={v!r}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


class MinimalRegressor:
    """
    Minimal trainable regressor: fits running mean of observed_cost from buffer.
    Same seed and same data -> same model state -> same checksum (determinism).
    """

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed
        self._n: int = 0
        self._sum: float = 0.0

    def fit(self, experience_buffer: list[dict[str, Any]]) -> None:
        """Update state from buffer entries that have observed_cost. Deterministic given buffer order and seed."""
        for d in experience_buffer:
            if isinstance(d, dict) and "observed_cost" in d:
                self._n += 1
                self._sum += float(d["observed_cost"])

    def predict(self, agent_id: str, work_id: str, device_id: str) -> float:
        """Predict cost (mean so far, or 0 if no data)."""
        if self._n == 0:
            return 0.0
        return self._sum / self._n

    def get_checksum(self) -> str:
        """Deterministic checksum of model state; same fit -> same checksum."""
        state = {"seed": self._seed, "n": self._n, "sum": self._sum}
        return _model_state_hash(state)


def predict_cost_checksum(
    agent_id: str,
    work_id: str,
    device_id: str,
    buffer_len: int,
    seed: int,
) -> str:
    """Deterministic checksum: same (agent_id, work_id, device_id, buffer_len, seed) -> same hash."""
    payload = f"{agent_id}|{work_id}|{device_id}|{buffer_len}|{seed}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def predict_cost(
    agent_id: str,
    work_id: str,
    device_id: str,
    experience_buffer: list[dict[str, Any]],
) -> float:
    """
    Placeholder: predict cost from experience buffer.
    Same seed/data -> same prediction (determinism). Returns 0.0 when buffer empty.
    Intentional placeholder: hash-based for determinism tests; replace with MinimalRegressor
    or a trained model for real learning-to-bid.
    """
    if not experience_buffer:
        return 0.0
    seed = 0
    for d in experience_buffer:
        if isinstance(d, dict) and "seed" in d:
            seed = int(d.get("seed", 0))
            break
    h = hash((agent_id, work_id, device_id, len(experience_buffer), seed))
    return float((h % 100) / 100.0)


def calibration_mae(
    experience_buffer: list[dict[str, Any]],
    predict_fn: Any = None,
) -> float:
    """
    Mean absolute error between predicted and observed cost over the buffer.
    Buffer entries: observed_cost, agent_id, work_id, device_id (and optional features).
    predict_fn(agent_id, work_id, device_id, buffer) used if provided; else predict_cost.
    Returns MAE over entries that have observed_cost; if no such entries, returns
    1.0 / (1 + len(experience_buffer)) as fallback.
    """
    if not experience_buffer:
        return 1.0
    pred_fn = predict_fn or predict_cost
    errors: list[float] = []
    for i, d in enumerate(experience_buffer):
        if not isinstance(d, dict) or "observed_cost" not in d:
            continue
        obs = float(d["observed_cost"])
        aid = d.get("agent_id", "a0")
        wid = d.get("work_id", "w0")
        did = d.get("device_id", "d0")
        pred = pred_fn(aid, wid, did, experience_buffer[: i + 1])
        errors.append(abs(pred - obs))
    if not errors:
        return 1.0 / (1 + len(experience_buffer))
    return sum(errors) / len(errors)
