"""
OpenAI Responses API backend with Structured Outputs (JSON Schema).

Production-grade live backend: strict schema, timeouts, bounded retries,
rate-limit handling, and RC_LLM_INVALID_OUTPUT on invalid schema.

- Only used when pipeline_mode=llm_live and allow_network is enabled.
- Single-step decision schema: action, args, reason_code, confidence, explanation_short.
- Maps response to ActionProposal (action_type, args, reason_code, token_refs, rationale, confidence, safety_notes).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, cast

from labtrust_gym.pipeline import check_network_allowed

LOG = logging.getLogger(__name__)

# Single-step decision schema for Responses API (strict)
SINGLE_STEP_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "args", "reason_code", "confidence", "explanation_short"],
    "properties": {
        "action": {"type": "string"},
        "args": {"type": "object"},
        "reason_code": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "explanation_short": {"type": "string", "maxLength": 280},
    },
}

# Tool definition: submit_action(action, args, reason_code, confidence, explanation_short)
SUBMIT_ACTION_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_action",
        "description": "Submit a single-step decision. Required: action (string), args (object), reason_code (string), confidence (0-1), explanation_short (string, max 280 chars).",
        "parameters": SINGLE_STEP_DECISION_SCHEMA,
    },
}

# Reason code when model returns invalid schema (must exist in reason_code_registry)
RC_LLM_INVALID_OUTPUT = "RC_LLM_INVALID_OUTPUT"

# Error tags for metrics
LLM_REFUSED = "LLM_REFUSED"
LLM_TIMEOUT = "LLM_TIMEOUT"
LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"

BACKEND_ID = "openai_responses"

# NOOP ActionProposal shape when backend fails or schema invalid
NOOP_ACTION_V01: dict[str, Any] = {
    "action_type": "NOOP",
    "args": {},
    "reason_code": None,
    "token_refs": [],
    "rationale": "Live backend error fallback.",
    "confidence": 0.0,
    "safety_notes": "",
}


def _get_config() -> tuple[str, str, int, int]:
    """Read config from environment. Returns (api_key, model, timeout_s, retries)."""
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    model = (os.environ.get("LABTRUST_OPENAI_MODEL") or "gpt-4o-mini").strip()
    try:
        timeout_s = int(os.environ.get("LABTRUST_LLM_TIMEOUT_S", "30"))
    except ValueError:
        timeout_s = 30
    if timeout_s <= 0:
        timeout_s = 30
    try:
        retries = int(os.environ.get("LABTRUST_LLM_RETRIES", "2"))
    except ValueError:
        retries = 2
    retries = min(max(0, retries), 5)
    return (api_key, model, timeout_s, retries)


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    """Percentile p (0..100). Returns None if empty."""
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (k - lo) * (sorted_vals[hi] - sorted_vals[lo])


def _usage_from_response(resp: Any) -> dict[str, int]:
    """Extract token usage from OpenAI response."""
    u = getattr(resp, "usage", None)
    if u is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {
        "prompt_tokens": int(getattr(u, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(u, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(u, "total_tokens", 0) or 0),
    }


def _decision_to_action_proposal(decision: dict[str, Any]) -> dict[str, Any]:
    """Map single-step decision to ActionProposal (action_type, args, reason_code, token_refs, rationale, confidence, safety_notes)."""
    return {
        "action_type": decision.get("action", "NOOP"),
        "args": decision.get("args") or {},
        "reason_code": decision.get("reason_code"),
        "token_refs": [],
        "rationale": decision.get("explanation_short") or "",
        "confidence": float(decision.get("confidence", 0.0)),
        "safety_notes": decision.get("explanation_short") or "",
    }


def _parse_and_validate_decision(
    raw_content: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Parse raw JSON and validate against single-step decision schema.
    Returns (decision_dict, None) on success, (None, error_reason) on failure.
    Used by both json_schema and tool_call paths so both produce identical Decision handling.
    """
    try:
        out = json.loads(raw_content)
    except json.JSONDecodeError:
        return (None, "LLM response was not valid JSON.")
    if not isinstance(out, dict):
        return (None, "LLM response was not a JSON object.")
    required = {"action", "args", "reason_code", "confidence", "explanation_short"}
    if not required.issubset(out.keys()):
        return (None, "LLM response missing required schema fields.")
    conf = out.get("confidence")
    if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
        return (None, "LLM confidence out of range [0,1].")
    expl = out.get("explanation_short")
    if expl is not None and (not isinstance(expl, str) or len(expl) > 280):
        return (None, "LLM explanation_short invalid or exceeds 280 chars.")
    return (out, None)


def _load_model_pricing(repo_root: Any | None = None) -> dict[str, Any]:
    """Load policy/llm/model_pricing.v0.1.yaml."""
    try:
        from pathlib import Path

        root = Path(repo_root) if repo_root else None
        if root is None:
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
    total_prompt_tokens: int,
    total_completion_tokens: int,
    repo_root: Any | None = None,
) -> float | None:
    """Estimated cost in USD from model_pricing.v0.1.yaml."""
    models = _load_model_pricing(repo_root)
    prices = models.get(model_id) if model_id else None
    if not prices or not isinstance(prices, dict):
        return None
    inp = prices.get("input_price_per_1m")
    out = prices.get("output_price_per_1m")
    if inp is None or out is None:
        return None
    try:
        return (total_prompt_tokens / 1_000_000.0) * float(inp) + (
            total_completion_tokens / 1_000_000.0
        ) * float(out)
    except (TypeError, ValueError):
        return None


class OpenAILiveResponsesBackend:
    """
    Live OpenAI backend using Responses API with Structured Outputs (JSON Schema).

    - Single-step decision schema: action, args, reason_code, confidence, explanation_short.
    - Strict schema adherence; invalid response -> NOOP + RC_LLM_INVALID_OUTPUT.
    - Timeouts, bounded retries, 429 backoff.
    - Only runs when pipeline_mode=llm_live and allow_network enabled.
    """

    supports_structured_outputs = True
    supports_tool_calls = True

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: int | None = None,
        retries: int | None = None,
        repo_root: Any | None = None,
        output_mode: str = "json_schema",
        prompts_policy: str = "v0.1",
        trace_collector: Any = None,
    ) -> None:
        key, mod, to, ret = _get_config()
        self._api_key = (api_key or key).strip()
        self._model = (model or mod).strip() or "gpt-4o-mini"
        self._timeout_s = timeout_s if timeout_s is not None else to
        self._retries = retries if retries is not None else ret
        self._repo_root = repo_root
        self._trace_collector = trace_collector
        self._output_mode = (
            output_mode
            if output_mode in ("json_schema", "tool_call")
            else "json_schema"
        )
        self._prompts_policy = "v0.2" if prompts_policy == "v0.2" else "v0.1"
        self._schema = SINGLE_STEP_DECISION_SCHEMA
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
        """Aggregate stats for results metadata: backend_id, model_id, latency p50/p95, tokens, cost."""
        rate = self._error_count / self._total_calls if self._total_calls > 0 else 0.0
        mean_ms = (
            self._sum_latency_ms / self._total_calls if self._total_calls > 0 else None
        )
        sorted_lat = sorted(self._latency_ms_list) if self._latency_ms_list else []
        p50_ms = _percentile(sorted_lat, 50)
        p95_ms = _percentile(sorted_lat, 95)
        tokens_per_step = (
            round(self._total_tokens / self._total_calls, 2)
            if self._total_calls > 0 and self._total_tokens
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
            "p50_llm_latency_ms": round(p50_ms, 2) if p50_ms is not None else None,
            "p95_llm_latency_ms": round(p95_ms, 2) if p95_ms is not None else None,
            "total_tokens": self._total_tokens,
            "tokens_per_step": tokens_per_step,
        }
        cost = _estimated_cost_usd(
            self._model,
            self._total_prompt_tokens,
            self._total_completion_tokens,
            self._repo_root,
        )
        if cost is not None:
            out["estimated_cost_usd"] = round(cost, 6)
        return out

    def propose_action(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Propose one action from context. Returns ActionProposal or NOOP on error.
        Invalid schema response -> NOOP with reason_code RC_LLM_INVALID_OUTPUT.
        """
        check_network_allowed()
        self._last_error_code = None
        self._last_metrics = {}
        prompt_fingerprint_this_call: str | None = None
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

        from labtrust_gym.baselines.llm.allowed_actions_payload import (
            build_allowed_actions_payload,
        )

        state_summary = context.get("state_summary") or {}
        allowed_actions = context.get("allowed_actions") or []
        allowed_actions_payload = build_allowed_actions_payload(
            state=state_summary,
            allowed_actions=allowed_actions,
        )
        repo_root = Path(self._repo_root) if self._repo_root else None
        if self._prompts_policy == "v0.2":
            from labtrust_gym.policy.prompts_v02 import render_prompt_v02

            system_content, user_content, prompt_fp = render_prompt_v02(
                role_id=str(context.get("role_id", "")),
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
                repo_root=repo_root,
            )
            prompt_fingerprint_this_call = prompt_fp
        else:
            from labtrust_gym.baselines.llm.prompts import (
                build_user_payload_from_context,
                DEVELOPER_PROMPT_ACTION_PROPOSAL,
                SYSTEM_PROMPT_ACTION_PROPOSAL,
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
            system_content = (
                SYSTEM_PROMPT_ACTION_PROPOSAL
                + "\n\n"
                + DEVELOPER_PROMPT_ACTION_PROPOSAL
            )
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]
        prompt_sha256 = _sha256(json.dumps(messages, sort_keys=True))
        start = time.perf_counter()
        try:
            if self._output_mode == "tool_call":
                raw, usage = self._call_api_tool_call(messages)
            else:
                raw, usage = self._call_api(messages)
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            self._last_error_code = (
                getattr(self, "_last_error_code", None) or LLM_PROVIDER_ERROR
            )
            self._error_count += 1
            self._sum_latency_ms += latency_ms
            noop = dict(NOOP_ACTION_V01)
            noop["reason_code"] = LLM_PROVIDER_ERROR
            self._last_metrics = {
                "model_id": self._model,
                "backend_id": BACKEND_ID,
                "latency_ms": round(latency_ms, 2),
                "prompt_sha256": prompt_sha256,
                "error_code": self._last_error_code,
                "error_message": str(e)[:200],
            }
            LOG.debug("OpenAI Responses backend error: %s", str(e)[:200])
            return noop

        latency_ms = (time.perf_counter() - start) * 1000
        self._sum_latency_ms += latency_ms
        self._latency_ms_list.append(latency_ms)
        self._total_tokens += usage.get("total_tokens", 0)
        self._total_prompt_tokens += usage.get("prompt_tokens", 0)
        self._total_completion_tokens += usage.get("completion_tokens", 0)
        response_sha256 = _sha256(raw)

        decision, parse_err = _parse_and_validate_decision(raw)
        if parse_err is not None:
            self._last_error_code = RC_LLM_INVALID_OUTPUT
            self._error_count += 1
            noop = dict(NOOP_ACTION_V01)
            noop["reason_code"] = RC_LLM_INVALID_OUTPUT
            noop["rationale"] = parse_err
            self._last_metrics = {
                "model_id": self._model,
                "backend_id": BACKEND_ID,
                "latency_ms": round(latency_ms, 2),
                "prompt_sha256": prompt_sha256,
                "response_sha256": response_sha256,
                "error_code": RC_LLM_INVALID_OUTPUT,
            }
            return noop

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
        if prompt_fingerprint_this_call is not None:
            self._last_metrics["prompt_fingerprint"] = prompt_fingerprint_this_call
        if self._trace_collector is not None:
            usage_with_latency = dict(usage)
            usage_with_latency["latency_ms"] = round(latency_ms, 2)
            self._trace_collector.record(messages, raw, prompt_sha256, usage_with_latency)
        return _decision_to_action_proposal(decision)

    def _call_api(self, messages: list[dict[str, str]]) -> tuple[str, dict[str, int]]:
        """
        Call OpenAI Chat Completions with response_format json_schema.
        Bounded retries with backoff on 429; timeout enforced.
        """
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai not installed; pip install -e '.[llm_openai]'"
            ) from e

        client = OpenAI(api_key=self._api_key)
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "single_step_decision",
                "strict": True,
                "schema": self._schema,
            },
        }
        attempt = 0
        last_exc: Exception | None = None
        max_attempts = self._retries + 1
        while attempt < max_attempts:
            try:
                resp = client.chat.completions.create(
                    model=self._model,
                    messages=cast(Any, messages),
                    response_format=cast(Any, response_format),
                    timeout=float(self._timeout_s),
                )
            except Exception as e:
                last_exc = e
                err_str = str(e).lower()
                if "timeout" in err_str or "timed out" in err_str:
                    self._last_error_code = LLM_TIMEOUT
                    raise
                if "429" in err_str or "rate" in err_str:
                    self._last_error_code = LLM_PROVIDER_ERROR
                    backoff = min(2.0**attempt, 30.0)
                    time.sleep(backoff)
                attempt += 1
                if attempt >= max_attempts:
                    raise
                continue
            choice = resp.choices[0] if resp.choices else None
            if not choice or not getattr(choice, "message", None):
                last_exc = RuntimeError("Empty response")
                attempt += 1
                if attempt >= max_attempts:
                    raise last_exc
                continue
            msg = choice.message
            if getattr(msg, "refusal", None):
                self._last_error_code = LLM_REFUSED
                raise RuntimeError(f"Refusal: {msg.refusal}")
            content = getattr(msg, "content", None) or ""
            if not content or not content.strip():
                last_exc = RuntimeError("Empty content")
                attempt += 1
                if attempt >= max_attempts:
                    raise last_exc
                continue
            usage = _usage_from_response(resp)
            return (content.strip(), usage)
        raise last_exc or RuntimeError("No response")

    def _call_api_tool_call(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str, dict[str, int]]:
        """
        Call OpenAI Chat Completions with tools=[submit_action] and tool_choice
        requiring that function. Returns (arguments_json_string, usage).
        """
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai not installed; pip install -e '.[llm_openai]'"
            ) from e

        client = OpenAI(api_key=self._api_key)
        tool_choice = {"type": "function", "function": {"name": "submit_action"}}
        attempt = 0
        last_exc: Exception | None = None
        max_attempts = self._retries + 1
        while attempt < max_attempts:
            try:
                resp = client.chat.completions.create(
                    model=self._model,
                    messages=cast(Any, messages),
                    tools=[SUBMIT_ACTION_TOOL],
                    tool_choice=cast(Any, tool_choice),
                    timeout=float(self._timeout_s),
                )
            except Exception as e:
                last_exc = e
                err_str = str(e).lower()
                if "timeout" in err_str or "timed out" in err_str:
                    self._last_error_code = LLM_TIMEOUT
                    raise
                if "429" in err_str or "rate" in err_str:
                    self._last_error_code = LLM_PROVIDER_ERROR
                    backoff = min(2.0**attempt, 30.0)
                    time.sleep(backoff)
                attempt += 1
                if attempt >= max_attempts:
                    raise
                continue
            choice = resp.choices[0] if resp.choices else None
            if not choice or not getattr(choice, "message", None):
                last_exc = RuntimeError("Empty response")
                attempt += 1
                if attempt >= max_attempts:
                    raise last_exc
                continue
            msg = choice.message
            if getattr(msg, "refusal", None):
                self._last_error_code = LLM_REFUSED
                raise RuntimeError(f"Refusal: {msg.refusal}")
            tool_calls = getattr(msg, "tool_calls", None) or []
            for tc in tool_calls:
                fn = getattr(tc, "function", None)
                if not fn:
                    continue
                if getattr(fn, "name", None) == "submit_action":
                    args_str = getattr(fn, "arguments", None) or ""
                    if not args_str.strip():
                        last_exc = RuntimeError("submit_action had empty arguments")
                        attempt += 1
                        if attempt >= max_attempts:
                            raise last_exc
                        continue
                    usage = _usage_from_response(resp)
                    return (args_str.strip(), usage)
            last_exc = RuntimeError("No submit_action tool call in response")
            attempt += 1
            if attempt >= max_attempts:
                raise last_exc
        raise last_exc or RuntimeError("No response")

    def healthcheck(self) -> dict[str, Any]:
        """
        One minimal request; returns dict with ok, model_id, latency_ms, usage, error.
        Caller must ensure pipeline_mode=llm_live and allow_network (e.g. via CLI).
        """
        check_network_allowed()
        if not self._api_key:
            return {
                "ok": False,
                "model_id": self._model,
                "latency_ms": None,
                "usage": {},
                "error": "OPENAI_API_KEY not set",
            }
        messages = [
            {
                "role": "system",
                "content": "You are a lab agent. Respond with a JSON object with keys: action, args, reason_code, confidence, explanation_short.",
            },
            {
                "role": "user",
                "content": "Health check: respond with action=NOOP, args={}, reason_code=null, confidence=1.0, explanation_short=OK.",
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
            if isinstance(data, dict) and "action" in data and "confidence" in data:
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
            "error": "Response did not match single-step decision schema",
        }
