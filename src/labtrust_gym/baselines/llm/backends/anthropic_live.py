"""
Live Anthropic backend: same llm_live interface as openai_live.

- Reads ANTHROPIC_API_KEY and LABTRUST_ANTHROPIC_MODEL from environment.
- Implements propose_action (ActionProposal via tool use), generate, healthcheck, get_aggregate_metrics.
- Uses one tool "propose_action" with input_schema = ActionProposal; parses tool_use block.
- Same metadata keys as openai_live: mean_latency_ms, backend_id, model_id, etc., for transparency aggregator.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from labtrust_gym.baselines.llm.backends.openai_live import (
    LLM_PROVIDER_ERROR,
    LLM_REFUSED,
    LLM_TIMEOUT,
    NOOP_ACTION_V01,
    _build_system_plus_developer,
)

BACKEND_ID = "anthropic_live"
LOG = logging.getLogger(__name__)

# Usage dict: input_tokens, output_tokens (Anthropic naming)
UsageDict = dict[str, int]


def _get_config() -> tuple[str, str, int]:
    """Read config from environment. Returns (api_key, model, timeout_s)."""
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    model = (
        os.environ.get("LABTRUST_ANTHROPIC_MODEL") or "claude-3-5-haiku-20241022"
    ).strip()
    try:
        timeout_s = int(os.environ.get("LABTRUST_LLM_TIMEOUT_S", "30"))
    except ValueError:
        timeout_s = 30
    if timeout_s <= 0:
        timeout_s = 30
    return (api_key, model, timeout_s)


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _action_proposal_schema_flat() -> dict[str, Any]:
    """ActionProposal schema for API (flat; no allOf). Same as openai_live."""
    return {
        "type": "object",
        "properties": {
            "action_type": {"type": "string", "minLength": 1},
            "args": {"type": "object", "additionalProperties": True},
            "reason_code": {
                "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}]
            },
            "token_refs": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            },
            "rationale": {"type": "string", "minLength": 1},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "safety_notes": {"type": "string"},
        },
        "required": [
            "action_type",
            "args",
            "reason_code",
            "token_refs",
            "rationale",
            "confidence",
            "safety_notes",
        ],
        "additionalProperties": False,
    }


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (k - lo) * (sorted_vals[hi] - sorted_vals[lo])


def _usage_from_anthropic(usage: Any) -> UsageDict:
    """Map Anthropic usage to common shape: prompt_tokens, completion_tokens, total_tokens."""
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    return {
        "prompt_tokens": inp,
        "completion_tokens": out,
        "total_tokens": inp + out,
    }


class AnthropicLiveBackend:
    """
    Live Anthropic backend; same interface as OpenAILiveBackend.

    - propose_action(context) -> ActionProposal dict or NOOP on error.
    - generate(messages) -> str (raw JSON).
    - healthcheck() -> {ok, model_id, latency_ms, usage, error}.
    - get_aggregate_metrics() -> backend_id, model_id, mean_latency_ms, etc. (canonical keys).
    """

    supports_structured_outputs = True
    supports_tool_calls = False

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: int | None = None,
        trace_collector: Any = None,
    ) -> None:
        key, mod, to = _get_config()
        self._api_key = (api_key or key).strip()
        self._model = (model or mod).strip() or "claude-3-5-haiku-20241022"
        self._timeout_s = timeout_s if timeout_s is not None else to
        self._schema = _action_proposal_schema_flat()
        self._system_plus_developer = _build_system_plus_developer()
        self._trace_collector = trace_collector
        self._last_error_code: str | None = None
        self._last_metrics: dict[str, Any] = {}
        self._total_calls: int = 0
        self._error_count: int = 0
        self._sum_latency_ms: float = 0.0
        self._total_tokens: int = 0
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._latency_ms_list: list[float] = []

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    @property
    def last_error_code(self) -> str | None:
        return self._last_error_code

    @property
    def last_metrics(self) -> dict[str, Any]:
        return dict(self._last_metrics)

    def get_aggregate_metrics(self) -> dict[str, Any]:
        """Same shape as openai_live: backend_id, model_id, mean_latency_ms, p50/p95, total_tokens, etc."""
        rate = self._error_count / self._total_calls if self._total_calls > 0 else 0.0
        mean_ms = (
            self._sum_latency_ms / self._total_calls if self._total_calls > 0 else None
        )
        sorted_lat = sorted(self._latency_ms_list) if self._latency_ms_list else []
        p50_ms = _percentile(sorted_lat, 50)
        p95_ms = _percentile(sorted_lat, 95)
        tokens_per_step = (
            round(self._total_tokens / self._total_calls, 2)
            if self._total_calls > 0 and self._total_tokens is not None
            else None
        )
        out: dict[str, Any] = {
            "backend_id": BACKEND_ID,
            "model_id": self._model,
            "total_calls": self._total_calls,
            "error_count": self._error_count,
            "error_rate": round(rate, 4),
            "sum_latency_ms": round(self._sum_latency_ms, 2),
            "mean_latency_ms": round(mean_ms, 2) if mean_ms is not None else None,
            "p50_latency_ms": round(p50_ms, 2) if p50_ms is not None else None,
            "p95_latency_ms": round(p95_ms, 2) if p95_ms is not None else None,
            "total_tokens": self._total_tokens,
            "tokens_per_step": tokens_per_step,
            "estimated_cost_usd": None,
        }
        return out

    def _call_api(self, messages: list[dict[str, str]]) -> tuple[str, UsageDict]:
        """Call Anthropic Messages API with one tool propose_action; return (content JSON str, usage)."""
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "anthropic not installed; pip install -e '.[llm_anthropic]'"
            ) from e

        client = anthropic.Anthropic(api_key=self._api_key)
        tool_def = {
            "name": "propose_action",
            "description": "Output exactly one ActionProposal JSON: action_type, args, reason_code, token_refs, rationale, confidence, safety_notes.",
            "input_schema": self._schema,
        }
        system = self._system_plus_developer
        user_content = ""
        for m in messages:
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                user_content = m["content"]
                break
            if m.get("role") == "user" and isinstance(m.get("content"), list):
                for block in m["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        user_content = block.get("text", "")
                        break
                break
        anthropic_messages: list[dict[str, Any]] = [
            {"role": "user", "content": [{"type": "text", "text": user_content}]}
        ]
        try:
            resp = client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=system,
                tools=[tool_def],
                tool_choice={"type": "tool", "name": "propose_action"},
                messages=anthropic_messages,
                timeout=float(self._timeout_s),
            )
        except anthropic.APIError as e:
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                self._last_error_code = LLM_TIMEOUT
            raise
        except Exception as e:
            if "refusal" in str(e).lower() or "refused" in str(e).lower():
                self._last_error_code = LLM_REFUSED
            raise

        usage = _usage_from_anthropic(getattr(resp, "usage", None))
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", None) == "tool_use":
                if getattr(block, "name", None) == "propose_action":
                    inp = getattr(block, "input", None)
                    if isinstance(inp, dict):
                        return (json.dumps(inp, sort_keys=True), usage)
                    if isinstance(inp, str):
                        return (inp, usage)
        raise RuntimeError("Anthropic response had no tool_use propose_action block")

    def propose_action(self, context: dict[str, Any]) -> dict[str, Any]:
        from labtrust_gym.baselines.llm.allowed_actions_payload import (
            build_allowed_actions_payload,
        )
        from labtrust_gym.baselines.llm.prompts import build_user_payload_from_context
        from labtrust_gym.pipeline import check_network_allowed

        check_network_allowed()
        self._last_error_code = None
        self._last_metrics = {}
        self._total_calls += 1
        if not self._api_key:
            self._last_error_code = LLM_PROVIDER_ERROR
            self._error_count += 1
            self._last_metrics = {
                "model_id": self._model,
                "backend_id": BACKEND_ID,
                "latency_ms": 0,
                "error_code": LLM_PROVIDER_ERROR,
            }
            return dict(NOOP_ACTION_V01)

        state_summary = context.get("state_summary") or {}
        allowed_actions = context.get("allowed_actions") or []
        allowed_actions_payload = build_allowed_actions_payload(
            state=state_summary,
            allowed_actions=allowed_actions,
        )
        user_content = build_user_payload_from_context(
            partner_id=context.get("partner_id", ""),
            policy_fingerprint=context.get("policy_fingerprint"),
            now_ts_s=int(context.get("now_ts_s", 0)),
            timing_mode=str(context.get("timing_mode", "explicit")),
            state_summary=state_summary,
            allowed_actions=allowed_actions,
            allowed_actions_payload=allowed_actions_payload,
            active_tokens=context.get("active_tokens"),
            recent_violations=context.get("recent_violations"),
            enforcement_state=context.get("enforcement_state"),
        )
        messages = [
            {"role": "system", "content": self._system_plus_developer},
            {"role": "user", "content": user_content},
        ]
        prompt_sha256 = _sha256(json.dumps(messages, sort_keys=True))
        start = time.perf_counter()
        try:
            raw, usage = self._call_api(messages)
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            self._last_error_code = getattr(
                self, "_last_error_code", None
            ) or LLM_PROVIDER_ERROR
            self._error_count += 1
            self._sum_latency_ms += latency_ms
            self._last_metrics = {
                "model_id": self._model,
                "backend_id": BACKEND_ID,
                "latency_ms": round(latency_ms, 2),
                "prompt_sha256": prompt_sha256,
                "error_code": self._last_error_code,
                "error_message": str(e)[:200],
            }
            LOG.debug("Anthropic backend error: %s", str(e)[:200])
            return dict(NOOP_ACTION_V01)
        latency_ms = (time.perf_counter() - start) * 1000
        self._sum_latency_ms += latency_ms
        self._latency_ms_list.append(latency_ms)
        self._total_tokens += usage.get("total_tokens", 0)
        self._total_prompt_tokens += usage.get("prompt_tokens", 0)
        self._total_completion_tokens += usage.get("completion_tokens", 0)
        response_sha256 = _sha256(raw)
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            self._last_error_code = LLM_PROVIDER_ERROR
            self._error_count += 1
            self._last_metrics = {
                "model_id": self._model,
                "backend_id": BACKEND_ID,
                "latency_ms": round(latency_ms, 2),
                "prompt_sha256": prompt_sha256,
                "response_sha256": response_sha256,
                "error_code": LLM_PROVIDER_ERROR,
            }
            return dict(NOOP_ACTION_V01)
        if not isinstance(out, dict):
            self._last_error_code = LLM_PROVIDER_ERROR
            self._error_count += 1
            self._last_metrics = {
                "model_id": self._model,
                "backend_id": BACKEND_ID,
                "latency_ms": round(latency_ms, 2),
                "prompt_sha256": prompt_sha256,
                "response_sha256": response_sha256,
                "error_code": LLM_PROVIDER_ERROR,
            }
            return dict(NOOP_ACTION_V01)
        self._last_metrics = {
            "model_id": self._model,
            "backend_id": BACKEND_ID,
            "latency_ms": round(latency_ms, 2),
            "prompt_sha256": prompt_sha256,
            "response_sha256": response_sha256,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "action_proposal": out,
        }
        if self._trace_collector is not None:
            self._trace_collector.record(messages, raw, prompt_sha256, usage)
        return out

    def generate(self, messages: list[dict[str, str]]) -> str:
        from labtrust_gym.pipeline import check_network_allowed

        check_network_allowed()
        self._last_error_code = None
        self._last_metrics = {}
        self._total_calls += 1
        if not self._api_key:
            self._last_error_code = LLM_PROVIDER_ERROR
            self._error_count += 1
            self._last_metrics = {
                "model_id": self._model,
                "backend_id": BACKEND_ID,
                "latency_ms": 0,
                "error_code": LLM_PROVIDER_ERROR,
            }
            return json.dumps(NOOP_ACTION_V01, sort_keys=True)
        prompt_sha256 = _sha256(json.dumps(messages, sort_keys=True))
        start = time.perf_counter()
        try:
            raw, usage = self._call_api(messages)
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            self._last_error_code = (
                getattr(self, "_last_error_code", None) or LLM_PROVIDER_ERROR
            )
            self._error_count += 1
            self._sum_latency_ms += latency_ms
            self._last_metrics = {
                "model_id": self._model,
                "backend_id": BACKEND_ID,
                "latency_ms": round(latency_ms, 2),
                "prompt_sha256": prompt_sha256,
                "error_code": self._last_error_code,
                "error_message": str(e)[:200],
            }
            LOG.debug("Anthropic backend error: %s", str(e)[:200])
            return json.dumps(NOOP_ACTION_V01, sort_keys=True)
        latency_ms = (time.perf_counter() - start) * 1000
        self._sum_latency_ms += latency_ms
        self._latency_ms_list.append(latency_ms)
        self._total_tokens += usage.get("total_tokens", 0)
        self._total_prompt_tokens += usage.get("prompt_tokens", 0)
        self._total_completion_tokens += usage.get("completion_tokens", 0)
        response_sha256 = _sha256(raw)
        self._last_metrics = {
            "model_id": self._model,
            "backend_id": BACKEND_ID,
            "latency_ms": round(latency_ms, 2),
            "prompt_sha256": prompt_sha256,
            "response_sha256": response_sha256,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
        return raw

    def healthcheck(self) -> dict[str, Any]:
        """Same shape as openai_live: ok, model_id, latency_ms, usage, error."""
        from labtrust_gym.pipeline import check_network_allowed

        check_network_allowed()
        if not self._api_key:
            return {
                "ok": False,
                "model_id": self._model,
                "latency_ms": None,
                "usage": {},
                "error": "ANTHROPIC_API_KEY not set",
            }
        messages = [
            {
                "role": "user",
                "content": "Return a single JSON object: action_type=NOOP, args={}, reason_code=null, token_refs=[], rationale=Health check, confidence=1.0, safety_notes=.",
            },
        ]
        start = time.perf_counter()
        try:
            raw, usage = self._call_api(messages)
            latency_ms = (time.perf_counter() - start) * 1000
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return {
                "ok": False,
                "model_id": self._model,
                "latency_ms": round(latency_ms, 2),
                "usage": {},
                "error": str(e)[:400],
            }
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "action_type" in data:
                return {
                    "ok": True,
                    "model_id": self._model,
                    "latency_ms": round(latency_ms, 2),
                    "usage": usage,
                    "error": None,
                }
        except json.JSONDecodeError:
            pass
        return {
            "ok": False,
            "model_id": self._model,
            "latency_ms": round(latency_ms, 2),
            "usage": usage,
            "error": "Response did not match ActionProposal schema",
        }


def _normalize_per_agent(
    per_agent: list[Any],
    allowed_agent_ids: list[str] | None = None,
    allowed_action_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Ensure each per_agent entry has agent_id (str), action_type (str), args (dict),
    reason_code (str or empty). Filter to allowed_agent_ids if provided; coerce
    invalid action_type to NOOP when allowed_action_types is provided.
    """
    out: list[dict[str, Any]] = []
    agent_set = set(allowed_agent_ids) if allowed_agent_ids else None
    for pa in per_agent or []:
        if not isinstance(pa, dict):
            continue
        aid = pa.get("agent_id")
        if aid is None:
            continue
        aid = str(aid).strip()
        if not aid:
            continue
        if agent_set is not None and aid not in agent_set:
            continue
        atype = str(pa.get("action_type") or "NOOP").strip()
        if allowed_action_types is not None and atype not in allowed_action_types:
            atype = "NOOP"
        args = pa.get("args")
        if not isinstance(args, dict):
            args = {}
        reason = pa.get("reason_code")
        if reason is not None:
            reason = str(reason)[:64]
        else:
            reason = ""
        out.append({
            "agent_id": aid,
            "action_type": atype,
            "args": dict(args),
            "reason_code": reason,
        })
    if allowed_agent_ids:
        seen = {p["agent_id"] for p in out}
        for aid in allowed_agent_ids:
            if aid not in seen:
                out.append({
                    "agent_id": aid,
                    "action_type": "NOOP",
                    "args": {},
                    "reason_code": "",
                })
    return out


def _anthropic_coord_fallback_proposal(
    agent_ids: list[str],
    step_id: int,
    method_id: str,
    seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Minimal valid CoordinationProposal (all NOOP) and meta for fallback."""
    proposal = {
        "proposal_id": f"fallback-anthropic-{seed}-{step_id}",
        "step_id": step_id,
        "method_id": method_id,
        "horizon_steps": 1,
        "per_agent": [
            {"agent_id": aid, "action_type": "NOOP", "args": {}, "reason_code": "COORD_BACKEND_ERROR"}
            for aid in agent_ids
        ],
        "comms": [],
        "meta": {"backend_id": "anthropic_live_coord", "model_id": "claude", "latency_ms": 0, "tokens_in": 0, "tokens_out": 0},
    }
    meta = {"backend_id": "anthropic_live_coord", "model_id": "claude", "latency_ms": 0.0, "tokens_in": 0, "tokens_out": 0}
    return proposal, meta


class AnthropicCoordinationProposalBackend:
    """
    Coordination proposal backend for llm_central_planner / llm_hierarchical_allocator.
    generate_proposal(state_digest, allowed_actions, step_id, method_id) -> (proposal_dict, meta).
    Uses Anthropic Messages API; on error returns minimal valid proposal (all NOOP).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: int | None = None,
        repo_root: Any | None = None,
    ) -> None:
        key, mod, to = _get_config()
        self._api_key = (api_key or key).strip()
        self._model = (model or mod).strip() or "claude-3-5-haiku-20241022"
        self._timeout_s = timeout_s if timeout_s is not None else to
        self._repo_root = repo_root
        self._seed = 0
        self._total_calls = 0
        self._error_count = 0
        self._sum_latency_ms = 0.0
        self._last_metrics: dict[str, Any] = {}

    def reset(self, seed: int) -> None:
        self._seed = seed

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        allowed_actions: list[str],
        step_id: int,
        method_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        from labtrust_gym.pipeline import check_network_allowed

        check_network_allowed()
        self._total_calls += 1
        agent_ids = [p.get("agent_id") for p in state_digest.get("per_agent") or []]
        if not agent_ids:
            agent_ids = ["ops_0"]
        fallback, fallback_meta = _anthropic_coord_fallback_proposal(
            agent_ids, step_id, method_id, self._seed
        )
        if not self._api_key:
            self._error_count += 1
            return (fallback, fallback_meta)
        try:
            import anthropic
        except ImportError:
            self._error_count += 1
            return (fallback, fallback_meta)
        state_payload = {
            "state_digest": state_digest,
            "allowed_actions": allowed_actions,
            "step_id": step_id,
            "method_id": method_id,
        }
        prompt = (
            "Return a single JSON object with keys: proposal_id, step_id, "
            "method_id, horizon_steps, per_agent (array of {agent_id, action_type, "
            "args, reason_code}), comms (array). State: "
            + json.dumps(state_payload, sort_keys=True)
            + ". Return only the JSON, no markdown."
        )
        start = time.perf_counter()
        try:
            client = anthropic.Anthropic(api_key=self._api_key)
            resp = client.messages.create(
                model=self._model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
                timeout=float(self._timeout_s),
            )
        except Exception:
            self._error_count += 1
            fallback_meta["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
            return (fallback, fallback_meta)
        latency_ms = (time.perf_counter() - start) * 1000
        usage = _usage_from_anthropic(getattr(resp, "usage", None))
        content = ""
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", None) == "text":
                content = getattr(block, "text", "") or ""
                break
        try:
            from labtrust_gym.baselines.llm.parse_utils import extract_first_json_object
            extracted = extract_first_json_object(content)
            if not extracted:
                self._error_count += 1
                fallback_meta["latency_ms"] = round(latency_ms, 2)
                fallback_meta["tokens_in"] = usage.get("prompt_tokens", 0)
                fallback_meta["tokens_out"] = usage.get("completion_tokens", 0)
                return (fallback, fallback_meta)
            proposal = json.loads(extracted)
        except (json.JSONDecodeError, TypeError):
            self._error_count += 1
            fallback_meta["latency_ms"] = round(latency_ms, 2)
            return (fallback, fallback_meta)
        if not isinstance(proposal, dict):
            self._error_count += 1
            return (fallback, fallback_meta)
        proposal.setdefault("per_agent", [])
        proposal.setdefault("comms", [])
        proposal["per_agent"] = _normalize_per_agent(
            proposal["per_agent"],
            allowed_agent_ids=agent_ids,
            allowed_action_types=set(allowed_actions or ["NOOP", "TICK", "MOVE", "START_RUN"]),
        )
        self._sum_latency_ms += latency_ms
        meta = {
            "backend_id": "anthropic_live_coord",
            "model_id": self._model,
            "latency_ms": round(latency_ms, 2),
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
        }
        self._last_metrics = meta
        return (proposal, meta)

    def get_aggregate_metrics(self) -> dict[str, Any]:
        n = self._total_calls
        rate = self._error_count / n if n > 0 else 0.0
        mean_ms = self._sum_latency_ms / n if n > 0 else None
        return {
            "backend_id": "anthropic_live_coord",
            "model_id": self._model,
            "error_rate": round(rate, 4),
            "mean_latency_ms": round(mean_ms, 2) if mean_ms is not None else None,
            **self._last_metrics,
        }


class AnthropicBidBackend:
    """
    Bid backend for llm_auction_bidder: generate_proposal(state_digest, step_id, method_id)
    -> (proposal_dict with market[], meta). Uses Anthropic; on failure returns minimal valid.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: int | None = None,
        repo_root: Any | None = None,
    ) -> None:
        key, mod, to = _get_config()
        self._api_key = (api_key or key).strip()
        self._model = (model or mod).strip() or "claude-3-5-haiku-20241022"
        self._timeout_s = timeout_s if timeout_s is not None else to
        self._repo_root = repo_root
        self._seed = 0
        self._last_metrics: dict[str, Any] = {}

    def reset(self, seed: int) -> None:
        self._seed = seed

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        step_id: int,
        method_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        from labtrust_gym.pipeline import check_network_allowed

        check_network_allowed()
        agent_ids = [p.get("agent_id") for p in state_digest.get("per_agent") or []]
        if not agent_ids:
            agent_ids = ["ops_0"]
        fallback = {
            "proposal_id": f"fallback-bid-anthropic-{self._seed}-{step_id}",
            "step_id": step_id,
            "method_id": method_id,
            "horizon_steps": 1,
            "per_agent": [],
            "comms": [],
            "market": [],
            "meta": {"backend_id": "anthropic_live_bid", "model_id": self._model, "latency_ms": 0, "tokens_in": 0, "tokens_out": 0},
        }
        fallback_meta = {"backend_id": "anthropic_live_bid", "model_id": self._model, "latency_ms": 0.0, "tokens_in": 0, "tokens_out": 0}
        if not self._api_key:
            return (fallback, fallback_meta)
        try:
            import anthropic
        except ImportError:
            return (fallback, fallback_meta)
        state_payload = {
            "state_digest": state_digest,
            "step_id": step_id,
            "method_id": method_id,
        }
        prompt = (
            "Return a single JSON object with: proposal_id, step_id, method_id, "
            "per_agent (array), comms (array), market (array of {agent_id, bid, "
            "bundle, constraints}). State: "
            + json.dumps(state_payload, sort_keys=True)
            + ". Return only the JSON."
        )
        start = time.perf_counter()
        try:
            client = anthropic.Anthropic(api_key=self._api_key)
            resp = client.messages.create(
                model=self._model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
                timeout=float(self._timeout_s),
            )
        except Exception:
            fallback_meta["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
            return (fallback, fallback_meta)
        latency_ms = (time.perf_counter() - start) * 1000
        usage = _usage_from_anthropic(getattr(resp, "usage", None))
        content = ""
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", None) == "text":
                content = getattr(block, "text", "") or ""
                break
        try:
            from labtrust_gym.baselines.llm.parse_utils import extract_first_json_object
            extracted = extract_first_json_object(content)
            if not extracted:
                fallback_meta["latency_ms"] = round(latency_ms, 2)
                fallback_meta["tokens_in"] = usage.get("prompt_tokens", 0)
                fallback_meta["tokens_out"] = usage.get("completion_tokens", 0)
                return (fallback, fallback_meta)
            proposal = json.loads(extracted)
        except (json.JSONDecodeError, TypeError):
            return (fallback, fallback_meta)
        if not isinstance(proposal, dict):
            return (fallback, fallback_meta)
        proposal.setdefault("market", [])
        proposal.setdefault("per_agent", [])
        proposal.setdefault("comms", [])
        proposal["per_agent"] = _normalize_per_agent(
            proposal["per_agent"],
            allowed_agent_ids=agent_ids,
        )
        meta = {
            "backend_id": "anthropic_live_bid",
            "model_id": self._model,
            "latency_ms": round(latency_ms, 2),
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
        }
        self._last_metrics = meta
        return (proposal, meta)

    def get_aggregate_metrics(self) -> dict[str, Any]:
        return dict(self._last_metrics)
