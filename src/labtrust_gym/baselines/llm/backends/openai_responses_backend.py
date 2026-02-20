"""
OpenAI live backend for generating CoordinationProposal objects (Responses API, structured outputs).

Opt-in only: used when llm_backend=openai_live for coordination methods. Never used by default.
Requires OPENAI_API_KEY; fail loudly if openai_live selected and key not set.
Does not log secrets; uses secret_scrubber. Stores redacted payload in logs for auditing.
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

LOG = logging.getLogger(__name__)

BACKEND_ID = "openai_live_coord"
REASON_OPENAI_API_KEY_MISSING = "OPENAI_API_KEY_MISSING"


def require_openai_api_key() -> str:
    """
    Return OPENAI_API_KEY if set. Raise ValueError with reason code if not set.
    Call before using openai_live for coordination.
    """
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise ValueError(
            f"{REASON_OPENAI_API_KEY_MISSING}: OPENAI_API_KEY must be set when using "
            "--llm-backend openai_live. Set the env var or use --llm-backend deterministic."
        )
    return key


def _coordination_proposal_schema_for_api() -> dict[str, Any]:
    """
    CoordinationProposal schema for OpenAI Structured Outputs (no $schema / refs).
    Matches policy/schemas/coordination_proposal.v0.1.schema.json required shape.
    """
    return {
        "type": "object",
        "properties": {
            "proposal_id": {"type": "string"},
            "step_id": {"type": "integer"},
            "method_id": {"type": "string"},
            "horizon_steps": {"type": "integer", "default": 1},
            "per_agent": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "action_type": {"type": "string"},
                        "args": {"type": "object", "additionalProperties": True},
                        "reason_code": {"type": "string"},
                        "confidence": {"type": "number"},
                        "token_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["agent_id", "action_type", "args", "reason_code"],
                    "additionalProperties": False,
                },
            },
            "comms": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from_agent_id": {"type": "string"},
                        "to_agent_id": {"type": "string"},
                        "channel": {"type": "string"},
                        "payload_typed": {"type": "object"},
                        "intent": {"type": "string"},
                        "ttl_steps": {"type": "integer"},
                        "broadcast": {"type": "boolean"},
                    },
                    "required": [
                        "from_agent_id",
                        "channel",
                        "payload_typed",
                        "intent",
                        "ttl_steps",
                    ],
                    "additionalProperties": False,
                },
            },
            "market": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "bid": {},
                        "bundle": {},
                        "constraints": {"type": "object"},
                    },
                    "required": ["agent_id"],
                    "additionalProperties": False,
                },
            },
            "meta": {
                "type": "object",
                "properties": {
                    "prompt_fingerprint": {"type": "string"},
                    "policy_fingerprint": {"type": "string"},
                    "backend_id": {"type": "string"},
                    "model_id": {"type": "string"},
                    "latency_ms": {"type": "number"},
                    "tokens_in": {"type": "integer"},
                    "tokens_out": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        "required": ["proposal_id", "step_id", "method_id", "per_agent", "comms", "meta"],
        "additionalProperties": False,
    }


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_model_pricing(repo_root: Path | None = None) -> dict[str, Any]:
    """Load policy/llm/model_pricing.v0.1.yaml. Returns {} if missing."""
    try:
        if repo_root is not None and repo_root.is_dir():
            root = repo_root
        else:
            try:
                from labtrust_gym.config import get_repo_root
                root = get_repo_root()
            except Exception:
                root = Path(__file__).resolve().parent.parent.parent.parent.parent
        path = root / "policy" / "llm" / "model_pricing.v0.1.yaml"
        if not path.exists():
            return {}
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data.get("models") or {}
    except Exception:
        return {}


def _estimated_cost_usd(
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    repo_root: Path | None = None,
) -> float | None:
    """Estimated cost in USD from model_pricing. Returns None if no pricing."""
    models = _load_model_pricing(repo_root)
    prices = models.get(model_id) if model_id else {}
    if not isinstance(prices, dict):
        return None
    inp = prices.get("input_price_per_1m")
    out = prices.get("output_price_per_1m")
    if inp is None or out is None:
        return None
    try:
        return (prompt_tokens / 1_000_000.0) * float(inp) + (
            completion_tokens / 1_000_000.0
        ) * float(out)
    except (TypeError, ValueError):
        return None


# Max conversation turns to keep for multi-turn (user+assistant pairs).
COORD_CONVERSATION_MAX_TURNS = 3


def generate_coordination_proposal(
    prompt: str,
    schema: dict[str, Any],
    timeout_s: int,
    retries: int = 1,
    model: str | None = None,
    api_key: str | None = None,
    *,
    conversation_history: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Call OpenAI Chat Completions with structured output for CoordinationProposal.

    Returns (proposal_dict, meta). proposal_dict conforms to coordination_proposal schema.
    meta: model_id, request_id, latency_ms, tokens_in, tokens_out, estimated_cost_usd (best-effort).
    When conversation_history is provided, meta may include conversation_history_updated (trimmed).
    Raises on API/key errors. Does not log raw prompt; logs redacted payload for auditing.
    """
    key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise ValueError(REASON_OPENAI_API_KEY_MISSING)
    model = (model or os.environ.get("LABTRUST_OPENAI_MODEL") or "gpt-4o-mini").strip()
    if conversation_history:
        system_content = (
            "You are a coordination planner. Output valid JSON only, conforming to the "
            "coordination proposal schema. No commentary outside the JSON."
        )
        messages = (
            [{"role": "system", "content": system_content}]
            + list(conversation_history)
            + [{"role": "user", "content": prompt}]
        )
    else:
        messages = [{"role": "user", "content": prompt}]
    prompt_fingerprint = _sha256(json.dumps(messages, sort_keys=True))
    start = time.perf_counter()
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(
            "openai not installed; pip install -e '.[llm_openai]'"
        ) from e
    client = OpenAI(api_key=key)
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "coordination_proposal_v01",
            "strict": True,
            "schema": schema,
        },
    }
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=cast(Any, messages),
                response_format=cast(Any, response_format),
                timeout=float(timeout_s),
            )
        except Exception as e:
            last_exc = e
            if attempt >= retries:
                raise
            continue
        choice = resp.choices[0] if resp.choices else None
        if not choice or not getattr(choice, "message", None):
            last_exc = RuntimeError("Empty response")
            if attempt >= retries:
                raise last_exc
            continue
        msg = choice.message
        content = getattr(msg, "content", None) or ""
        if not content or not content.strip():
            last_exc = RuntimeError("Empty content")
            if attempt >= retries:
                raise last_exc
            continue
        latency_ms = (time.perf_counter() - start) * 1000
        usage = getattr(resp, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
        request_id = getattr(resp, "id", None) or ""
        try:
            proposal = json.loads(content.strip())
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON from API: {e}") from e
        if not isinstance(proposal, dict):
            raise RuntimeError("API response is not a JSON object")
        redacted = scrub_dict_for_log(proposal)
        LOG.debug(
            "Coordination proposal (redacted) request_id=%s latency_ms=%.1f",
            request_id[:20] if request_id else "",
            latency_ms,
        )
        if LOG.isEnabledFor(logging.DEBUG):
            safe_log = scrub_secrets(json.dumps(redacted, sort_keys=True)[:2000])
            LOG.debug("Proposal payload (redacted): %s...", safe_log[:500])
        cost = _estimated_cost_usd(model, prompt_tokens, completion_tokens)
        meta = {
            "backend_id": BACKEND_ID,
            "model_id": model,
            "request_id": request_id,
            "latency_ms": round(latency_ms, 2),
            "tokens_in": prompt_tokens,
            "tokens_out": completion_tokens,
            "estimated_cost_usd": round(cost, 6) if cost is not None else None,
            "prompt_fingerprint": prompt_fingerprint,
        }
        if "meta" not in proposal or not isinstance(proposal.get("meta"), dict):
            proposal["meta"] = {}
        proposal["meta"].update(
            {k: v for k, v in meta.items() if k != "prompt_fingerprint"}
        )
        if conversation_history is not None:
            new_user = {"role": "user", "content": prompt}
            new_assistant = {"role": "assistant", "content": content}
            updated = list(conversation_history) + [new_user, new_assistant]
            max_msgs = COORD_CONVERSATION_MAX_TURNS * 2
            if len(updated) > max_msgs:
                updated = updated[-max_msgs:]
            meta["conversation_history_updated"] = updated
        return (proposal, meta)
    raise last_exc or RuntimeError("No response")


class OpenAICoordinationProposalBackend:
    """
    Proposal backend for LLM coordination methods: generates CoordinationProposal
    via OpenAI Responses API (structured outputs). Opt-in only; requires OPENAI_API_KEY.

    Interface: reset(seed), generate_proposal(state_digest, allowed_actions, step_id, method_id)
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
        allowed_actions: list[str],
        step_id: int,
        method_id: str,
        *,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Return (proposal_dict, meta). Builds prompt from state_digest; calls OpenAI;
        returns dict conforming to coordination_proposal schema. On error returns
        a minimal valid proposal (all NOOP) and meta with error info.
        When conversation_history is provided, multi-turn is used and meta may
        include conversation_history_updated for the next step.
        """
        from labtrust_gym.pipeline import check_network_allowed
        check_network_allowed()

        self._total_calls += 1
        agent_ids = [p.get("agent_id") for p in state_digest.get("per_agent") or []]
        if not agent_ids:
            agent_ids = ["ops_0"]
        fallback_proposal = {
            "proposal_id": f"fallback-{self._seed}-{step_id}",
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
            self._last_metrics = {
                "backend_id": BACKEND_ID,
                "model_id": self._model,
                "error_code": REASON_OPENAI_API_KEY_MISSING,
            }
            return (fallback_proposal, fallback_meta)

        tracer = None
        try:
            from labtrust_gym.baselines.llm.llm_tracer import get_llm_tracer
            tracer = get_llm_tracer()
        except Exception:
            pass
        if tracer is not None:
            tracer.start_span("coord_proposal")
            tracer.set_attribute("backend_id", BACKEND_ID)
            tracer.set_attribute("model_id", self._model)

        prompt = json.dumps(
            {
                "state_digest": state_digest,
                "allowed_actions": allowed_actions,
                "step_id": step_id,
                "method_id": method_id,
            },
            sort_keys=True,
        )
        try:
            proposal, meta = generate_coordination_proposal(
                prompt=prompt,
                schema=self._schema,
                timeout_s=self._timeout_s,
                retries=self._retries,
                model=self._model,
                api_key=self._api_key,
                conversation_history=conversation_history,
            )
        except Exception as e:
            if tracer is not None:
                tracer.set_attribute("latency_ms", 0)
                tracer.end_span("error", str(e)[:200])
            self._error_count += 1
            self._last_metrics = {
                "backend_id": BACKEND_ID,
                "model_id": self._model,
                "error_code": getattr(e, "args", [""])[0] if getattr(e, "args", None) else str(e)[:200],
            }
            LOG.debug("Coordination proposal API error: %s", scrub_secrets(str(e)[:200]))
            return (fallback_proposal, fallback_meta)

        if tracer is not None:
            tracer.set_attribute("latency_ms", meta.get("latency_ms"))
            tracer.set_attribute("prompt_tokens", meta.get("tokens_in"))
            tracer.set_attribute("completion_tokens", meta.get("tokens_out"))
            if meta.get("estimated_cost_usd") is not None:
                tracer.set_attribute("estimated_cost_usd", meta["estimated_cost_usd"])
            tracer.end_span()
        self._sum_latency_ms += meta.get("latency_ms", 0)
        self._total_tokens_in += meta.get("tokens_in", 0)
        self._total_tokens_out += meta.get("tokens_out", 0)
        self._latency_ms_list.append(meta.get("latency_ms", 0))
        self._last_metrics = dict(meta)
        self._last_response_redacted = scrub_dict_for_log(proposal)
        return (proposal, meta)

    def get_aggregate_metrics(self) -> dict[str, Any]:
        """
        Aggregate over all generate_proposal calls. Used by runner for results.metadata.
        Returns: backend_id, model_id, mean_latency_ms, p50/p95, tokens_per_step,
        estimated_cost_usd, error_rate.
        """
        n = self._total_calls
        rate = self._error_count / n if n > 0 else 0.0
        mean_ms = self._sum_latency_ms / n if n > 0 else None
        sorted_lat = sorted(self._latency_ms_list) if self._latency_ms_list else []
        p50 = (
            sorted_lat[int((len(sorted_lat) - 1) * 0.50)]
            if sorted_lat else None
        )
        p95 = (
            sorted_lat[int((len(sorted_lat) - 1) * 0.95)]
            if sorted_lat else None
        )
        total_tok = self._total_tokens_in + self._total_tokens_out
        tokens_per_step = round(total_tok / n, 2) if n > 0 and total_tok is not None else None
        cost = _estimated_cost_usd(
            self._model,
            self._total_tokens_in,
            self._total_tokens_out,
            self._repo_root,
        )
        return {
            "backend_id": BACKEND_ID,
            "model_id": self._model,
            "error_rate": round(rate, 4),
            "mean_latency_ms": round(mean_ms, 2) if mean_ms is not None else None,
            "p50_latency_ms": round(p50, 2) if p50 is not None else None,
            "p95_latency_ms": round(p95, 2) if p95 is not None else None,
            "total_tokens": total_tok,
            "tokens_per_step": tokens_per_step,
            "estimated_cost_usd": round(cost, 6) if cost is not None else None,
        }


class OpenAILocalProposalBackend:
    """
    Local proposal backend for llm_local_decider_signed_bus: propose_action(local_view,
    allowed_actions, agent_id, step) -> ActionProposal dict. Wraps OpenAILiveBackend
    with minimal context built from local_view.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        repo_root: Path | None = None,
    ) -> None:
        from labtrust_gym.baselines.llm.backends.openai_live import OpenAILiveBackend
        self._backend = OpenAILiveBackend(api_key=api_key, model=model)

    def reset(self, seed: int) -> None:
        pass

    def propose_action(
        self,
        local_view: dict[str, Any],
        allowed_actions: list[str],
        agent_id: str,
        step: int,
    ) -> dict[str, Any]:
        """Return ActionProposal dict (action_type, args, reason_code, etc.)."""
        context = {
            "state_summary": local_view,
            "allowed_actions": allowed_actions,
            "partner_id": agent_id,
            "policy_fingerprint": None,
            "now_ts_s": step,
            "timing_mode": "explicit",
            "active_tokens": None,
            "recent_violations": None,
            "enforcement_state": None,
        }
        return self._backend.propose_action(context)

    def get_aggregate_metrics(self) -> dict[str, Any]:
        return getattr(self._backend, "get_aggregate_metrics", lambda: {})()

    @property
    def last_metrics(self) -> dict[str, Any]:
        return getattr(self._backend, "last_metrics", lambda: {})()


def _minimal_gossip_payload(agent_id: str, t: int) -> dict[str, Any]:
    """Minimal valid gossip payload for fallback when LLM fails."""
    return {
        "agent_id": agent_id[:64],
        "step_id": t,
        "zone_id": "",
        "queue_summary": [],
        "task": "active",
    }


class OpenAIGossipSummaryBackend:
    """
    Live summary backend for llm_gossip_summarizer: get_summary(agent_id, obs,
    zone_ids, device_ids, t) -> dict. Returns gossip payload (agent_id, step_id,
    zone_id, queue_summary, task). On API/parse error returns minimal valid payload.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        repo_root: Path | None = None,
    ) -> None:
        from labtrust_gym.baselines.llm.backends.openai_live import OpenAILiveBackend
        self._backend = OpenAILiveBackend(api_key=api_key, model=model)

    def get_summary(
        self,
        agent_id: str,
        obs: dict[str, Any],
        zone_ids: list[str],
        device_ids: list[str],
        t: int,
    ) -> dict[str, Any]:
        """Return gossip payload dict. On failure return minimal valid payload."""
        from labtrust_gym.baselines.coordination.obs_utils import (
            get_queue_by_device,
            get_zone_from_obs,
            log_frozen,
        )
        o = obs.get(agent_id) or {}
        zone = get_zone_from_obs(o, zone_ids) or str(o.get("zone_id", ""))[:64]
        task = "frozen" if log_frozen(o) else "active"
        qbd = get_queue_by_device(o)
        queue_preview: list[dict[str, Any]] = []
        for idx, dev_id in enumerate((device_ids or [])[:12]):
            if idx >= len(qbd):
                break
            d = qbd[idx] if isinstance(qbd[idx], dict) else {}
            queue_preview.append({
                "device_id": str(d.get("device_id", dev_id))[:32],
                "queue_len": min(1024, max(0, int(d.get("queue_len", 0)))),
                "queue_head": str(d.get("queue_head", ""))[:64],
            })
        prompt = (
            "Return a single JSON object with keys: agent_id (string), step_id "
            "(int), zone_id (string), queue_summary (array of objects with "
            "device_id, queue_len, queue_head), task (string 'active' or 'frozen'). "
            "agent_id=%s step_id=%s zone_id=%s task=%s queue_preview=%s. "
            "Return only the JSON, no markdown."
        ) % (
            agent_id,
            t,
            zone,
            task,
            json.dumps(queue_preview, sort_keys=True),
        )
        messages = [{"role": "user", "content": prompt}]
        try:
            raw = self._backend.generate(messages)
        except Exception:
            return _minimal_gossip_payload(agent_id, t)
        raw = (raw or "").strip()
        for part in (raw.split("```") if "```" in raw else [raw]):
            part = part.strip()
            if part.startswith("json") or part.startswith("{"):
                raw = part.replace("json", "", 1).strip()
                break
        try:
            from labtrust_gym.baselines.llm.parse_utils import (
                extract_first_json_object,
            )
            extracted = extract_first_json_object(raw)
            if not extracted:
                return _minimal_gossip_payload(agent_id, t)
            out = json.loads(extracted)
        except (json.JSONDecodeError, TypeError):
            return _minimal_gossip_payload(agent_id, t)
        if not isinstance(out, dict):
            return _minimal_gossip_payload(agent_id, t)
        out.setdefault("agent_id", agent_id[:64])
        out.setdefault("step_id", t)
        out.setdefault("zone_id", str(out.get("zone_id", ""))[:64])
        out.setdefault("queue_summary", [])
        if not isinstance(out["queue_summary"], list):
            out["queue_summary"] = []
        out.setdefault("task", "active")
        if out["task"] not in ("active", "frozen"):
            out["task"] = "active"
        return out
