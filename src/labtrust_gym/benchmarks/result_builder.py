"""
Result payload helpers for the benchmark runner.

Pure functions for building canonical results.v0.2 structures
(e.g. LLM economics block). Used by runner.run_benchmark when
assembling the final results dict before write.
"""

from __future__ import annotations

from typing import Any


def normalize_llm_economics(
    raw_llm: dict[str, Any] | None,
    raw_llm_repair: dict[str, Any] | None,
    steps: int,
) -> dict[str, Any]:
    """
    Build results.v0.2 canonical coordination.llm block: call_count,
    total_tokens, tokens_per_step, mean_latency_ms, p95_latency_ms,
    error_rate, invalid_output_rate, estimated_cost_usd.
    Fills 0 / null for missing or deterministic.
    """
    raw = raw_llm or {}
    repair = raw_llm_repair or {}
    steps = max(1, steps)

    calls_main = (
        raw.get("call_count")
        if raw.get("call_count") is not None
        else int(raw.get("proposal_total_count") or 0)
    )
    calls_repair = int(repair.get("repair_call_count") or 0)
    call_count = calls_main + calls_repair

    tokens_in = int(raw.get("tokens_in") or 0)
    tokens_out = int(raw.get("tokens_out") or 0)
    tokens_repair = int(repair.get("total_repair_tokens") or 0)
    total_tokens = tokens_in + tokens_out + tokens_repair
    tokens_per_step = round((total_tokens / steps), 4) if total_tokens else 0.0

    lat_list = raw.get("latency_ms_list") or []
    if repair.get("mean_repair_latency_ms") is not None and calls_repair:
        lat_list = list(lat_list) + [
            repair["mean_repair_latency_ms"],
        ] * max(0, calls_repair - 1)
    mean_latency_ms: float | None = raw.get("latency_ms")
    if mean_latency_ms is None and repair.get("mean_repair_latency_ms") is not None:
        mean_latency_ms = repair["mean_repair_latency_ms"]
    if mean_latency_ms is None and lat_list:
        valid = [float(x) for x in lat_list if x is not None]
        mean_latency_ms = round(sum(valid) / len(valid), 2) if valid else None
    p95_latency_ms: float | None = None
    if lat_list:
        valid = sorted(float(x) for x in lat_list if x is not None)
        if valid:
            k = (len(valid) - 1) * 0.95
            lo = int(k)
            hi = min(lo + 1, len(valid) - 1)
            p95_latency_ms = round(
                valid[lo] + (k - lo) * (valid[hi] - valid[lo]), 2
            )

    invalid_main = 0
    if calls_main and raw.get("proposal_total_count"):
        valid_count = int(raw.get("proposal_valid_count") or 0)
        prop_total = int(raw.get("proposal_total_count") or 0)
        invalid_main = max(0, prop_total - valid_count)
    invalid_repair = int(repair.get("repair_fallback_noop_count") or 0)
    total_calls = call_count or 1
    invalid_output_rate = round(
        (invalid_main + invalid_repair) / total_calls, 4
    )

    cost = raw.get("estimated_cost_usd")
    if cost is None:
        cost = repair.get("estimated_cost_usd")
    if cost is not None:
        try:
            cost = float(cost)
        except (TypeError, ValueError):
            cost = None

    out: dict[str, Any] = {
        "call_count": call_count,
        "total_tokens": total_tokens,
        "tokens_per_step": tokens_per_step,
        "mean_latency_ms": mean_latency_ms,
        "p95_latency_ms": p95_latency_ms,
        "error_rate": float(raw.get("error_rate") or 0.0),
        "invalid_output_rate": invalid_output_rate,
        "estimated_cost_usd": cost,
    }
    if repair.get("fault_injected_rate") is not None:
        out["fault_injected_rate"] = repair["fault_injected_rate"]
    if repair.get("fallback_rate") is not None:
        out["fallback_rate"] = repair["fallback_rate"]
    return out
