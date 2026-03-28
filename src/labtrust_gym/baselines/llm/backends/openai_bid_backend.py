"""
OpenAI live backend for auction bidder: generates CoordinationProposal with market[]
bids via OpenAI structured outputs. Opt-in only; requires OPENAI_API_KEY.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
    _estimated_cost_usd,
    generate_coordination_proposal,
)
from labtrust_gym.security.secret_scrubber import scrub_dict_for_log, scrub_secrets

LOG = logging.getLogger(__name__)

BACKEND_ID = "openai_live_bid"


def _bid_proposal_schema_for_api() -> dict[str, Any]:
    """
    Lightweight schema for auction bidder outputs.

    This path only consumes `market`, so requiring full coordination-proposal
    shape (per_agent/comms/etc.) increases structured-output failures.
    """
    return {
        "type": "object",
        "properties": {
            "proposal_id": {"type": "string"},
            "step_id": {"type": "integer"},
            "method_id": {"type": "string"},
            "market": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "bid": {},
                        "bundle": {},
                        "constraints": {"type": "object"},
                        "units": {"type": "string"},
                    },
                    "required": ["agent_id"],
                    "additionalProperties": False,
                },
            },
            "per_agent": {"type": "array"},
            "comms": {"type": "array"},
            "meta": {"type": "object"},
        },
        "required": ["proposal_id", "step_id", "method_id", "market"],
        "additionalProperties": False,
    }


def _build_bid_prompt(state_digest: dict[str, Any], step_id: int, method_id: str) -> str:
    """Build a prompt that asks for market bids (agent_id, bid, bundle, constraints)."""
    per_agent = state_digest.get("per_agent") or []
    per_device = state_digest.get("per_device") or []
    compact_agents: list[dict[str, Any]] = []
    for a in per_agent[:8]:
        if not isinstance(a, dict):
            continue
        compact_agents.append(
            {
                "agent_id": a.get("agent_id"),
                "zone": a.get("zone"),
                "role": a.get("role"),
            }
        )
    compact_devices: list[dict[str, Any]] = []
    for d in per_device[:12]:
        if not isinstance(d, dict):
            continue
        compact_devices.append(
            {
                "device_id": d.get("device_id"),
                "queue_head": d.get("queue_head"),
                "queue_len": d.get("queue_len"),
                "zone": d.get("zone"),
            }
        )
    payload = {
        "step_id": step_id,
        "method_id": method_id,
        "per_agent": compact_agents,
        "per_device": compact_devices,
    }
    return (
        "You are a coordination auction. Given the state digest, produce a valid JSON object "
        "with: proposal_id (string), step_id (integer), method_id (string), per_agent (array, "
        "can be empty), comms (array, empty), market (array of {agent_id, bid, bundle, constraints}), "
        "meta (object with backend_id, model_id). Each market entry: agent_id string, bid number, "
        "bundle object (e.g. device_id, work_id), constraints object. Prefer empty per_agent and comms.\n\n"
        "IMPORTANT: keep output compact; include at most 8 market entries, each with a valid bundle.\n\n"
        + json.dumps(payload, sort_keys=True)
    )


class OpenAIBidBackend:
    """
    Bid backend for llm_auction_bidder: generates CoordinationProposal with market[]
    via OpenAI. Interface: reset(seed), generate_proposal(state_digest, step_id, method_id)
    -> (proposal_dict, meta). get_aggregate_metrics() for runner metadata.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: int = 30,
        retries: int = 1,
        repo_root: Path | None = None,
        *,
        openai_base_url: str | None = None,
        openai_default_headers: dict[str, str] | None = None,
        meta_backend_id: str | None = None,
    ) -> None:
        self._api_key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
        self._model = (model or os.environ.get("LABTRUST_OPENAI_MODEL") or "gpt-4o-mini").strip()
        self._timeout_s = max(5, timeout_s)
        self._retries = max(0, retries)
        self._repo_root = Path(repo_root) if repo_root else None
        self._openai_base_url = (openai_base_url or "").strip() or None
        self._openai_default_headers = dict(openai_default_headers) if openai_default_headers else None
        self._meta_backend_id = meta_backend_id or BACKEND_ID
        self._schema = _bid_proposal_schema_for_api()
        self._seed = 0
        self._total_calls = 0
        self._error_count = 0
        self._sum_latency_ms = 0.0
        self._total_tokens_in = 0
        self._total_tokens_out = 0
        self._latency_ms_list: list[float] = []
        self._last_metrics: dict[str, Any] = {}
        self._last_response_redacted: dict[str, Any] | None = None
        self._last_error_code: str | None = None

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    @property
    def last_metrics(self) -> dict[str, Any]:
        return dict(self._last_metrics)

    def reset(self, seed: int) -> None:
        self._seed = seed

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        step_id: int,
        method_id: str,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (proposal_dict with market[], meta). On error return minimal valid proposal and meta."""
        from labtrust_gym.pipeline import check_network_allowed

        check_network_allowed()

        self._total_calls += 1
        agent_ids = [p.get("agent_id") for p in state_digest.get("per_agent") or []]
        if not agent_ids:
            agent_ids = ["ops_0"]
        fallback = {
            "proposal_id": f"fallback-bid-{self._seed}-{step_id}",
            "step_id": step_id,
            "method_id": method_id,
            "horizon_steps": 1,
            "per_agent": [],
            "comms": [],
            "market": [],
            "meta": {
                "backend_id": self._meta_backend_id,
                "model_id": self._model,
                "latency_ms": 0,
                "tokens_in": 0,
                "tokens_out": 0,
            },
        }
        fallback_meta = {
            "backend_id": self._meta_backend_id,
            "model_id": self._model,
            "latency_ms": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
            "estimated_cost_usd": None,
        }

        if not self._api_key:
            self._error_count += 1
            self._last_error_code = "OPENAI_API_KEY_MISSING"
            self._last_metrics = {**fallback_meta, "error_code": self._last_error_code}
            return (fallback, fallback_meta)

        tracer = None
        try:
            from labtrust_gym.baselines.llm.llm_tracer import get_llm_tracer

            tracer = get_llm_tracer()
        except Exception:
            pass
        if tracer is not None:
            tracer.start_span("coord_bid")
            tracer.set_attribute("backend_id", self._meta_backend_id)
            tracer.set_attribute("model_id", self._model)

        prompt = _build_bid_prompt(state_digest, step_id, method_id)
        try:
            proposal, meta = generate_coordination_proposal(
                prompt=prompt,
                schema=self._schema,
                timeout_s=self._timeout_s,
                retries=self._retries,
                model=self._model,
                api_key=self._api_key,
                openai_base_url=self._openai_base_url,
                default_headers=self._openai_default_headers,
                meta_backend_id=self._meta_backend_id,
            )
        except Exception as e:
            # Rescue path: retry with a much smaller prompt that asks for
            # compact/empty market payload. This absorbs transient parse/size
            # failures while keeping live-call evidence and valid outputs.
            try:
                rescue_prompt = (
                    "Return valid JSON with fields proposal_id, step_id, method_id, market. "
                    "Use this exact step_id and method_id. market may be empty [].\n\n"
                    + json.dumps(
                        {
                            "step_id": step_id,
                            "method_id": method_id,
                            "agent_ids": agent_ids[:8],
                        },
                        sort_keys=True,
                    )
                )
                proposal, meta = generate_coordination_proposal(
                    prompt=rescue_prompt,
                    schema=self._schema,
                    timeout_s=max(10, int(self._timeout_s // 2)),
                    retries=max(self._retries, 1),
                    model=self._model,
                    api_key=self._api_key,
                    openai_base_url=self._openai_base_url,
                    default_headers=self._openai_default_headers,
                    meta_backend_id=self._meta_backend_id,
                )
            except Exception:
                if tracer is not None:
                    tracer.set_attribute("latency_ms", 0)
                    tracer.end_span("error", str(e)[:200])
                LOG.debug("OpenAI bid backend error: %s", scrub_secrets(str(e)[:200]))
                self._error_count += 1
                self._last_error_code = str(e)[:180]
                self._last_metrics = {**fallback_meta, "error_code": self._last_error_code}
                return (fallback, fallback_meta)

        if tracer is not None:
            tracer.set_attribute("latency_ms", meta.get("latency_ms"))
            tracer.set_attribute("prompt_tokens", meta.get("tokens_in"))
            tracer.set_attribute("completion_tokens", meta.get("tokens_out"))
            if meta.get("estimated_cost_usd") is not None:
                tracer.set_attribute("estimated_cost_usd", meta["estimated_cost_usd"])
            tracer.end_span()
        if not isinstance(proposal.get("market"), list):
            proposal["market"] = []
        self._sum_latency_ms += meta.get("latency_ms") or 0
        self._total_tokens_in += meta.get("tokens_in") or 0
        self._total_tokens_out += meta.get("tokens_out") or 0
        self._latency_ms_list.append(meta.get("latency_ms") or 0)
        self._last_error_code = None
        self._last_metrics = dict(meta)
        self._last_response_redacted = scrub_dict_for_log(proposal)
        return (proposal, meta)

    def get_aggregate_metrics(self) -> dict[str, Any]:
        """Return backend_id, model_id, error_rate, mean_latency_ms, p50/p95, total_tokens, tokens_per_step, estimated_cost_usd."""
        n = self._total_calls
        total_tok = (self._total_tokens_in or 0) + (self._total_tokens_out or 0)
        tokens_per_step = round(total_tok / n, 2) if n > 0 and total_tok else None
        err_rate = self._error_count / n if n > 0 else 0.0
        latencies = sorted(self._latency_ms_list) if self._latency_ms_list else []
        mean_lat = self._sum_latency_ms / n if n > 0 else None
        p50 = latencies[len(latencies) // 2] if latencies else None
        p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else (latencies[0] if latencies else None)
        cost = _estimated_cost_usd(
            self._model,
            self._total_tokens_in,
            self._total_tokens_out,
            self._repo_root,
        )
        return {
            "backend_id": self._meta_backend_id,
            "model_id": self._model,
            "total_calls": n,
            "error_count": self._error_count,
            "sum_latency_ms": round(self._sum_latency_ms, 2),
            "error_rate": round(err_rate, 4),
            "mean_latency_ms": round(mean_lat, 2) if mean_lat is not None else None,
            "p50_latency_ms": round(p50, 2) if p50 is not None else None,
            "p95_latency_ms": round(p95, 2) if p95 is not None else None,
            "total_tokens": total_tok,
            "tokens_per_step": tokens_per_step,
            "estimated_cost_usd": round(cost, 6) if cost is not None else None,
            "last_error_code": self._last_error_code,
        }
