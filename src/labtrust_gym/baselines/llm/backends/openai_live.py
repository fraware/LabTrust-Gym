"""
Live OpenAI backend with Structured Outputs (opt-in).

- Reads OPENAI_API_KEY and LABTRUST_OPENAI_MODEL from environment only (no .env).
- Implements ProviderBackend (propose_action -> ActionProposal) and LLMBackend (generate -> str).
- Uses ActionProposal schema with OpenAI Structured Outputs; NOOP on error with tagged metrics.
- Per-provider code: isolated behind optional extra llm_openai; engine logic uses ProviderBackend only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

# Usage dict: prompt_tokens, completion_tokens, total_tokens (from API)
UsageDict = Dict[str, int]

# NOOP shape for error fallback (ActionProposal v0.1)
NOOP_ACTION_V01: Dict[str, Any] = {
    "action_type": "NOOP",
    "args": {},
    "reason_code": None,
    "token_refs": [],
    "rationale": "Live backend error fallback.",
    "confidence": 0.0,
    "safety_notes": "",
}

# Error tags for metrics (must match reason_code_registry)
LLM_REFUSED = "LLM_REFUSED"
LLM_TIMEOUT = "LLM_TIMEOUT"
LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"

BACKEND_ID = "openai_live"
LOG = logging.getLogger(__name__)


def _get_config() -> Tuple[str, str, int, int]:
    """Read config from environment only. Returns (api_key, model, timeout_s, retries)."""
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    model = (os.environ.get("LABTRUST_OPENAI_MODEL") or "gpt-4o-mini").strip()
    try:
        timeout_s = int(os.environ.get("LABTRUST_LLM_TIMEOUT_S", "20"))
    except ValueError:
        timeout_s = 20
    if timeout_s <= 0:
        timeout_s = 20
    try:
        retries = int(os.environ.get("LABTRUST_LLM_RETRIES", "0"))
    except ValueError:
        retries = 0
    retries = max(0, retries)
    return (api_key, model, timeout_s, retries)


def _action_proposal_schema_for_api() -> Dict[str, Any]:
    """
    ActionProposal schema for OpenAI API (no allOf/if/then; API unsupported).
    Full validation is done locally with action_proposal.v0.1.
    """
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


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _percentile(sorted_vals: List[float], p: float) -> Optional[float]:
    """Percentile p (0..100). Returns None if empty."""
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (k - lo) * (sorted_vals[hi] - sorted_vals[lo])


def _load_model_pricing(repo_root: Optional[Any] = None) -> Dict[str, Any]:
    """Load policy/llm/model_pricing.v0.1.yaml. Returns {} if missing."""
    try:
        from pathlib import Path

        if repo_root is not None:
            root = Path(repo_root)
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
    total_prompt_tokens: int,
    total_completion_tokens: int,
    repo_root: Optional[Any] = None,
) -> Optional[float]:
    """Compute estimated cost in USD from model_pricing.v0.1.yaml. Returns None if no pricing."""
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


def _build_system_plus_developer() -> str:
    """Prompt Pack v1: system + developer combined."""
    from labtrust_gym.baselines.llm.prompts import (
        DEVELOPER_PROMPT_ACTION_PROPOSAL,
        SYSTEM_PROMPT_ACTION_PROPOSAL,
    )

    return SYSTEM_PROMPT_ACTION_PROPOSAL + "\n\n" + DEVELOPER_PROMPT_ACTION_PROPOSAL


class OpenAILiveBackend:
    """
    Live OpenAI backend with Structured Outputs. Opt-in only; no keys in default path.

    Implements ProviderBackend (propose_action) and LLMBackend (generate).
    - Reads OPENAI_API_KEY, LABTRUST_OPENAI_MODEL, LABTRUST_LLM_TIMEOUT_S,
      LABTRUST_LLM_RETRIES from environment only.
    - propose_action(context) -> dict (ActionProposal or NOOP on error).
    - generate(messages) -> str for LLMBackend protocol.
    - On refusal/timeout/provider error: NOOP and last_error_code for metrics.
    - Does not log raw prompts; last_metrics has prompt_sha256, response_sha256.
    - Capability flags: supports_structured_outputs=True (best quality), supports_tool_calls=False.
    """

    supports_structured_outputs = True
    supports_tool_calls = False

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: Optional[int] = None,
        retries: Optional[int] = None,
    ) -> None:
        key, mod, to, ret = _get_config()
        self._api_key = (api_key or key).strip()
        self._model = (model or mod).strip() or "gpt-4o-mini"
        self._timeout_s = timeout_s if timeout_s is not None else to
        self._retries = retries if retries is not None else ret
        self._schema = _action_proposal_schema_for_api()
        self._system_plus_developer = _build_system_plus_developer()
        self._last_error_code: Optional[str] = None
        self._last_metrics: Dict[str, Any] = {}
        self._total_calls: int = 0
        self._error_count: int = 0
        self._sum_latency_ms: float = 0.0
        self._total_tokens: int = 0
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._latency_ms_list: List[float] = []

    @property
    def is_available(self) -> bool:
        """True if API key is set (backend can be used)."""
        return bool(self._api_key)

    @property
    def last_error_code(self) -> Optional[str]:
        """Set after propose_action/generate on refusal/timeout/error."""
        return self._last_error_code

    @property
    def last_metrics(self) -> Dict[str, Any]:
        """model_id, backend_id, latency_ms, prompt_sha256, response_sha256."""
        return dict(self._last_metrics)

    def get_aggregate_metrics(self) -> Dict[str, Any]:
        """
        Aggregate stats over all generate/propose_action calls since init or last reset.
        Returns: backend_id, model_id, total_calls, error_count, error_rate, sum_latency_ms,
        mean_latency_ms, p50_latency_ms, p95_latency_ms, total_tokens, tokens_per_step,
        estimated_cost_usd (when model_pricing available).
        """
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
        out: Dict[str, Any] = {
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
        }
        cost = _estimated_cost_usd(
            self._model,
            self._total_prompt_tokens,
            self._total_completion_tokens,
        )
        if cost is not None:
            out["estimated_cost_usd"] = round(cost, 6)
        return out

    def propose_action(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Propose one action from context. Returns ActionProposal dict or NOOP on error.

        context: partner_id, policy_fingerprint, now_ts_s, timing_mode,
        state_summary, allowed_actions, active_tokens, recent_violations,
        enforcement_state.
        """
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

        from labtrust_gym.baselines.llm.allowed_actions_payload import (
            build_allowed_actions_payload,
        )
        from labtrust_gym.baselines.llm.prompts import (
            build_user_payload_from_context,
        )

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
            self._last_error_code = LLM_PROVIDER_ERROR
            self._error_count += 1
            self._sum_latency_ms += latency_ms
            self._last_metrics = {
                "model_id": self._model,
                "backend_id": BACKEND_ID,
                "latency_ms": round(latency_ms, 2),
                "prompt_sha256": prompt_sha256,
                "error_code": LLM_PROVIDER_ERROR,
                "error_message": str(e)[:200],
            }
            LOG.debug("OpenAI backend error: %s", str(e)[:200])
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
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
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
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
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
        return out

    def _call_api(self, messages: List[Dict[str, str]]) -> Tuple[str, UsageDict]:
        """Call OpenAI Chat Completions with Structured Outputs. Returns (content, usage)."""
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
                "name": "action_proposal_v01",
                "strict": True,
                "schema": self._schema,
            },
        }
        attempt = 0
        last_exc: Optional[Exception] = None
        while attempt <= self._retries:
            try:
                resp = client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    response_format=response_format,
                    timeout=float(self._timeout_s),
                )
            except Exception as e:
                last_exc = e
                if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                    self._last_error_code = LLM_TIMEOUT
                    raise
                attempt += 1
                if attempt > self._retries:
                    raise
                continue
            choice = resp.choices[0] if resp.choices else None
            if not choice or not getattr(choice, "message", None):
                last_exc = RuntimeError("Empty response")
                attempt += 1
                if attempt > self._retries:
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
                if attempt > self._retries:
                    raise last_exc
                continue
            usage = _usage_from_response(resp)
            return (content.strip(), usage)
        raise last_exc or RuntimeError("No response")


def _usage_from_response(resp: Any) -> UsageDict:
    """Extract prompt_tokens, completion_tokens, total_tokens from OpenAI response."""
    u = getattr(resp, "usage", None)
    if u is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {
        "prompt_tokens": int(getattr(u, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(u, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(u, "total_tokens", 0) or 0),
    }

    def generate(self, messages: List[Dict[str, str]]) -> str:
        """LLMBackend protocol: return raw JSON string. Uses messages as-is for API."""
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
            LOG.debug("OpenAI backend error: %s", str(e)[:200])
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
