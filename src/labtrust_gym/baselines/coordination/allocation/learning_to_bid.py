"""
Learning-to-bid: lightweight regressor from experience buffer.
Predict service time / success probability / QC-fail risk; bidder uses predicted cost.
Clearing stays deterministic. Optional module.
"""

from __future__ import annotations

import hashlib
from typing import Any


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
    Stub: returns 1/(1+len(buffer)) when buffer has observed_cost keys.
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
