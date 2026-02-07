"""
OpenAI live backend for auction bidder: generates CoordinationProposal with market[]
bids via OpenAI structured outputs. Opt-in only; requires OPENAI_API_KEY.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, cast

from labtrust_gym.security.secret_scrubber import scrub_dict_for_log, scrub_secrets

from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
    _coordination_proposal_schema_for_api,
    _estimated_cost_usd,
    _load_model_pricing,
    generate_coordination_proposal,
)

LOG = logging.getLogger(__name__)

BACKEND_ID = "openai_live_bid"


def _build_bid_prompt(state_digest: dict[str, Any], step_id: int, method_id: str) -> str:
    """Build a prompt that asks for market bids (agent_id, bid, bundle, constraints)."""
    per_agent = state_digest.get("per_agent") or []
    per_device = state_digest.get("per_device") or []
    payload = {
        "step_id": step_id,
        "method_id": method_id,
        "per_agent": per_agent[:20],
        "per_device": per_device[:30],
    }
    return (
        "You are a coordination auction. Given the state digest, produce a valid JSON object "
        "with: proposal_id (string), step_id (integer), method_id (string), per_agent (array, "
        "can be empty), comms (array, empty), market (array of {agent_id, bid, bundle, constraints}), "
        "meta (object with backend_id, model_id). Each market entry: agent_id string, bid number, "
        "bundle object (e.g. device_id, work_id), constraints object. Prefer empty per_agent and comms.\n\n"
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
    ) -> None:
        self._api_key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
        self._model = (model or os.environ.get("LABTRUST_OPENAI_MODEL") or "gpt-4o-mini").strip()
        self._timeout_s = max(5, timeout_s)
        self._retries = max(0, retries)
        self._repo_root = Path(repo_root) if repo_root else None
        self._schema = _coordination_proposal_schema_for_api()
        self._seed = 0
        self._total_calls = 0
        self._error_count = 0
        self._sum_latency_ms = 0.0
        self._total_tokens_in = 0
        self._total_tokens_out = 0
        self._latency_ms_list: list[float] = []
        self._last_metrics: dict[str, Any] = {}
        self._last_response_redacted: dict[str, Any] | None = None

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
                "backend_id": BACKEND_ID,
                "model_id": self._model,
                "latency_ms": 0,
                "tokens_in": 0,
                "tokens_out": 0,
            },
        }
        fallback_meta = {
            "backend_id": BACKEND_ID,
            "model_id": self._model,
            "latency_ms": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
            "estimated_cost_usd": None,
        }

        if not self._api_key:
            self._error_count += 1
            self._last_metrics = fallback_meta
            return (fallback, fallback_meta)

        prompt = _build_bid_prompt(state_digest, step_id, method_id)
        try:
            proposal, meta = generate_coordination_proposal(
                prompt=prompt,
                schema=self._schema,
                timeout_s=self._timeout_s,
                retries=self._retries,
                model=self._model,
                api_key=self._api_key,
            )
        except Exception as e:
            LOG.debug("OpenAI bid backend error: %s", scrub_secrets(str(e)[:200]))
            self._error_count += 1
            self._last_metrics = fallback_meta
            return (fallback, fallback_meta)

        if not isinstance(proposal.get("market"), list):
            proposal["market"] = []
        self._sum_latency_ms += meta.get("latency_ms") or 0
        self._total_tokens_in += meta.get("tokens_in") or 0
        self._total_tokens_out += meta.get("tokens_out") or 0
        self._latency_ms_list.append(meta.get("latency_ms") or 0)
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
            "backend_id": BACKEND_ID,
            "model_id": self._model,
            "error_rate": round(err_rate, 4),
            "mean_latency_ms": round(mean_lat, 2) if mean_lat is not None else None,
            "p50_latency_ms": round(p50, 2) if p50 is not None else None,
            "p95_latency_ms": round(p95, 2) if p95 is not None else None,
            "total_tokens": total_tok if total_tok else None,
            "tokens_per_step": tokens_per_step,
            "estimated_cost_usd": round(cost, 6) if cost is not None else None,
        }
