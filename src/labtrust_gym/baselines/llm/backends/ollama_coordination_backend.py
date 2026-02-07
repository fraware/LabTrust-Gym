"""
Ollama live backend for coordination: proposal and bid backends.

Same interface as OpenAI coordination backends; uses local Ollama API.
No schema enforcement; parses JSON from response with fallback to minimal valid
proposal on parse failure. Requires allow_network when used.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from labtrust_gym.baselines.llm.backends.ollama_live import _get_config
from labtrust_gym.baselines.llm.parse_utils import extract_first_json_object

LOG = logging.getLogger(__name__)

BACKEND_ID_COORD = "ollama_live_coord"
BACKEND_ID_BID = "ollama_live_bid"


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _call_ollama_chat(prompt: str, base_url: str, model: str, timeout_s: int) -> str:
    """POST to Ollama /api/chat with single user message. Returns content."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data.get("message")
    if not isinstance(msg, dict):
        raise RuntimeError("Ollama response missing message")
    content = msg.get("content")
    if content is None:
        return "{}"
    return str(content).strip()


def _minimal_proposal(
    agent_ids: list[str],
    step_id: int,
    method_id: str,
    seed: int,
    backend_id: str,
    model: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Minimal valid CoordinationProposal (all NOOP) and meta for fallback."""
    proposal = {
        "proposal_id": f"fallback-{seed}-{step_id}",
        "step_id": step_id,
        "method_id": method_id,
        "horizon_steps": 1,
        "per_agent": [
            {
                "agent_id": aid,
                "action_type": "NOOP",
                "args": {},
                "reason_code": "COORD_BACKEND_ERROR",
            }
            for aid in agent_ids
        ],
        "comms": [],
        "meta": {
            "backend_id": backend_id,
            "model_id": model,
            "latency_ms": 0,
            "tokens_in": 0,
            "tokens_out": 0,
        },
    }
    meta = {
        "backend_id": backend_id,
        "model_id": model,
        "latency_ms": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
    }
    return proposal, meta


def _ensure_proposal_shape(proposal: dict[str, Any], agent_ids: list[str]) -> None:
    """Ensure required keys exist; fill per_agent with NOOP for missing agents."""
    proposal.setdefault("proposal_id", "ollama-proposal")
    proposal.setdefault("step_id", 0)
    proposal.setdefault("method_id", "llm_constrained")
    proposal.setdefault("horizon_steps", 1)
    proposal.setdefault("comms", [])
    if "per_agent" not in proposal or not isinstance(proposal["per_agent"], list):
        proposal["per_agent"] = []
    per_agent_by_id = {
        p.get("agent_id"): p for p in proposal["per_agent"] if p.get("agent_id")
    }
    for aid in agent_ids:
        if aid not in per_agent_by_id:
            proposal["per_agent"].append({
                "agent_id": aid,
                "action_type": "NOOP",
                "args": {},
                "reason_code": "LLM_INVALID_SCHEMA",
            })
    if "meta" not in proposal or not isinstance(proposal.get("meta"), dict):
        proposal["meta"] = {}


class OllamaCoordinationProposalBackend:
    """
    Proposal backend for LLM coordination (central planner, hierarchical).
    generate_proposal(...) -> (proposal_dict, meta). Uses Ollama /api/chat;
    on parse failure returns minimal valid proposal (all NOOP).
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: int | None = None,
    ) -> None:
        url, mod, to = _get_config()
        self._base_url = (base_url or url).rstrip("/") + "/"
        self._model = (model or mod).strip() or "llama3.2"
        self._timeout_s = timeout_s if timeout_s is not None else to
        self._seed = 0
        self._total_calls = 0
        self._error_count = 0
        self._sum_latency_ms = 0.0
        self._latency_ms_list: list[float] = []
        self._last_metrics: dict[str, Any] = {}

    @property
    def is_available(self) -> bool:
        return bool(self._base_url)

    @property
    def last_metrics(self) -> dict[str, Any]:
        return dict(self._last_metrics)

    def reset(self, seed: int) -> None:
        self._seed = seed

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        allowed_actions: list[str],
        step_id: int,
        method_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (proposal_dict, meta). On error or parse failure return minimal valid proposal."""
        from labtrust_gym.pipeline import check_network_allowed

        check_network_allowed()

        self._total_calls += 1
        agent_ids = [p.get("agent_id") for p in state_digest.get("per_agent") or []]
        if not agent_ids:
            agent_ids = ["ops_0"]
        fallback_proposal, fallback_meta = _minimal_proposal(
            agent_ids,
            step_id,
            method_id,
            self._seed,
            BACKEND_ID_COORD,
            self._model,
        )

        prompt = (
            "Return a single JSON object: coordination proposal with keys "
            "proposal_id (string), step_id (int), method_id (string), "
            "horizon_steps (int), per_agent (array of {agent_id, action_type, "
            "args, reason_code}), comms (array), meta (object). "
            "Use only action types from allowed_actions. State digest:\n"
            + json.dumps(
                {
                    "state_digest": state_digest,
                    "allowed_actions": allowed_actions,
                    "step_id": step_id,
                    "method_id": method_id,
                },
                sort_keys=True,
            )
        )
        start = time.perf_counter()
        try:
            raw = _call_ollama_chat(
                prompt, self._base_url, self._model, self._timeout_s
            )
        except Exception as e:
            LOG.debug("Ollama coord backend error: %s", str(e)[:200])
            self._error_count += 1
            self._last_metrics = fallback_meta
            return (fallback_proposal, fallback_meta)

        latency_ms = (time.perf_counter() - start) * 1000
        extracted = extract_first_json_object(raw)
        if not extracted:
            LOG.debug("Ollama coord: no JSON object in response")
            self._error_count += 1
            fallback_meta["latency_ms"] = round(latency_ms, 2)
            self._last_metrics = fallback_meta
            return (fallback_proposal, fallback_meta)
        try:
            proposal = json.loads(extracted)
        except json.JSONDecodeError:
            LOG.debug("Ollama coord: invalid JSON")
            self._error_count += 1
            fallback_meta["latency_ms"] = round(latency_ms, 2)
            self._last_metrics = fallback_meta
            return (fallback_proposal, fallback_meta)
        if not isinstance(proposal, dict):
            self._error_count += 1
            fallback_meta["latency_ms"] = round(latency_ms, 2)
            self._last_metrics = fallback_meta
            return (fallback_proposal, fallback_meta)

        _ensure_proposal_shape(proposal, agent_ids)
        proposal["step_id"] = step_id
        proposal["method_id"] = method_id
        if "meta" not in proposal:
            proposal["meta"] = {}
        proposal["meta"].update({
            "backend_id": BACKEND_ID_COORD,
            "model_id": self._model,
            "latency_ms": round(latency_ms, 2),
            "tokens_in": 0,
            "tokens_out": 0,
        })
        meta = {
            "backend_id": BACKEND_ID_COORD,
            "model_id": self._model,
            "latency_ms": round(latency_ms, 2),
            "tokens_in": 0,
            "tokens_out": 0,
            "prompt_fingerprint": _sha256(prompt),
        }
        self._sum_latency_ms += latency_ms
        self._latency_ms_list.append(latency_ms)
        self._last_metrics = meta
        return (proposal, meta)

    def get_aggregate_metrics(self) -> dict[str, Any]:
        n = self._total_calls
        rate = self._error_count / n if n > 0 else 0.0
        mean_ms = self._sum_latency_ms / n if n > 0 else None
        sorted_lat = sorted(self._latency_ms_list) if self._latency_ms_list else []
        p50 = sorted_lat[len(sorted_lat) // 2] if sorted_lat else None
        p95 = (
            sorted_lat[int((len(sorted_lat) - 1) * 0.95)]
            if len(sorted_lat) > 1
            else (sorted_lat[0] if sorted_lat else None)
        )
        return {
            "backend_id": BACKEND_ID_COORD,
            "model_id": self._model,
            "error_rate": round(rate, 4),
            "mean_latency_ms": (
                round(mean_ms, 2) if mean_ms is not None else None
            ),
            "p50_latency_ms": round(p50, 2) if p50 is not None else None,
            "p95_latency_ms": round(p95, 2) if p95 is not None else None,
            "total_tokens": None,
            "tokens_per_step": None,
            "estimated_cost_usd": None,
        }


class OllamaBidBackend:
    """
    Bid backend for llm_auction_bidder: generate_proposal(state_digest, step_id,
    method_id) -> (proposal_dict with market[], meta). Uses Ollama; on failure
    returns minimal valid.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: int | None = None,
    ) -> None:
        url, mod, to = _get_config()
        self._base_url = (base_url or url).rstrip("/") + "/"
        self._model = (model or mod).strip() or "llama3.2"
        self._timeout_s = timeout_s if timeout_s is not None else to
        self._seed = 0
        self._total_calls = 0
        self._error_count = 0
        self._sum_latency_ms = 0.0
        self._latency_ms_list: list[float] = []
        self._last_metrics: dict[str, Any] = {}

    @property
    def is_available(self) -> bool:
        return bool(self._base_url)

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
        """Return (proposal_dict with market[], meta). On failure minimal valid."""
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
                "backend_id": BACKEND_ID_BID,
                "model_id": self._model,
                "latency_ms": 0,
                "tokens_in": 0,
                "tokens_out": 0,
            },
        }
        fallback_meta = {
            "backend_id": BACKEND_ID_BID,
            "model_id": self._model,
            "latency_ms": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
        }

        prompt = (
            "Return a single JSON object with: proposal_id (string), step_id (int), "
            "method_id (string), per_agent (array, can be empty), comms (array, "
            "empty), market (array of {agent_id, bid, bundle, constraints}), "
            "meta (object). State digest:\n"
            + json.dumps(
                {
                    "state_digest": state_digest,
                    "step_id": step_id,
                    "method_id": method_id,
                },
                sort_keys=True,
            )
        )
        start = time.perf_counter()
        try:
            raw = _call_ollama_chat(
                prompt,
                self._base_url,
                self._model,
                self._timeout_s,
            )
        except Exception as e:
            LOG.debug("Ollama bid backend error: %s", str(e)[:200])
            self._error_count += 1
            self._last_metrics = fallback_meta
            return (fallback, fallback_meta)

        latency_ms = (time.perf_counter() - start) * 1000
        extracted = extract_first_json_object(raw)
        if not extracted:
            self._error_count += 1
            fallback_meta["latency_ms"] = round(latency_ms, 2)
            self._last_metrics = fallback_meta
            return (fallback, fallback_meta)
        try:
            proposal = json.loads(extracted)
        except json.JSONDecodeError:
            self._error_count += 1
            fallback_meta["latency_ms"] = round(latency_ms, 2)
            self._last_metrics = fallback_meta
            return (fallback, fallback_meta)
        if not isinstance(proposal, dict):
            self._error_count += 1
            fallback_meta["latency_ms"] = round(latency_ms, 2)
            self._last_metrics = fallback_meta
            return (fallback, fallback_meta)

        if not isinstance(proposal.get("market"), list):
            proposal["market"] = []
        proposal.setdefault("per_agent", [])
        proposal.setdefault("comms", [])
        if "meta" not in proposal:
            proposal["meta"] = {}
        proposal["meta"].update(
            {
                "backend_id": BACKEND_ID_BID,
                "model_id": self._model,
                "latency_ms": round(latency_ms, 2),
                "tokens_in": 0,
                "tokens_out": 0,
            }
        )
        meta = {
            "backend_id": BACKEND_ID_BID,
            "model_id": self._model,
            "latency_ms": round(latency_ms, 2),
            "tokens_in": 0,
            "tokens_out": 0,
        }
        self._sum_latency_ms += latency_ms
        self._latency_ms_list.append(latency_ms)
        self._last_metrics = meta
        return (proposal, meta)

    def get_aggregate_metrics(self) -> dict[str, Any]:
        n = self._total_calls
        rate = self._error_count / n if n > 0 else 0.0
        mean_ms = self._sum_latency_ms / n if n > 0 else None
        sorted_lat = sorted(self._latency_ms_list) if self._latency_ms_list else []
        p50 = sorted_lat[len(sorted_lat) // 2] if sorted_lat else None
        p95 = (
            sorted_lat[int((len(sorted_lat) - 1) * 0.95)]
            if len(sorted_lat) > 1
            else (sorted_lat[0] if sorted_lat else None)
        )
        return {
            "backend_id": BACKEND_ID_BID,
            "model_id": self._model,
            "error_rate": round(rate, 4),
            "mean_latency_ms": (
                round(mean_ms, 2) if mean_ms is not None else None
            ),
            "p50_latency_ms": round(p50, 2) if p50 is not None else None,
            "p95_latency_ms": round(p95, 2) if p95 is not None else None,
            "total_tokens": None,
            "tokens_per_step": None,
            "estimated_cost_usd": None,
        }
