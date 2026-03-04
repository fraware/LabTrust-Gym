"""
Live OpenAI backend with Structured Outputs (opt-in).

- Reads OPENAI_API_KEY and LABTRUST_OPENAI_MODEL from environment only (no .env).
- Implements ProviderBackend (propose_action -> ActionProposal) and LLMBackend (generate -> str).
- Uses ActionProposal schema with OpenAI Structured Outputs; NOOP on error with tagged metrics.
- Per-provider code: isolated behind optional extra llm_openai; engine logic uses ProviderBackend only.

SOTA resilience (opt-in via env):
- Fallback chain: LABTRUST_OPENAI_FALLBACK_MODEL (comma-separated list); try each on refusal/timeout.
- Request cache: LABTRUST_LLM_REQUEST_CACHE=1, _MAX_SIZE, _TTL_S; skip API for identical prompt hash.
- Prompt caching: LABTRUST_LLM_PROMPT_CACHE_KEY, LABTRUST_LLM_PROMPT_CACHE_RETENTION (in_memory|24h).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, cast

# Usage dict: prompt_tokens, completion_tokens, total_tokens (from API)
UsageDict = dict[str, int]

# NOOP shape for error fallback (ActionProposal v0.1)
NOOP_ACTION_V01: dict[str, Any] = {
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


# Max conversation turns (user+assistant pairs) to include in context for multi-turn.
MAX_CONVERSATION_HISTORY_TURNS = 6

# Max backoff seconds between retries (exponential backoff cap).
MAX_BACKOFF_S = 60


def _get_config() -> tuple[str, str, list[str], int, int]:
    """
    Read config from environment.
    Returns (api_key, model, fallback_models, timeout_s, retries).
    fallback_models: list of model ids (comma-separated in env); excludes primary.
    """
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    model = (os.environ.get("LABTRUST_OPENAI_MODEL") or "gpt-4o-mini").strip()
    fallback_raw = (os.environ.get("LABTRUST_OPENAI_FALLBACK_MODEL") or "").strip()
    fallback_models = [m.strip() for m in fallback_raw.split(",") if m.strip()] if fallback_raw else []
    if model in fallback_models:
        fallback_models = [m for m in fallback_models if m != model]
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
    return (api_key, model, fallback_models, timeout_s, retries)


def _action_proposal_schema_for_api() -> dict[str, Any]:
    """
    ActionProposal schema for OpenAI API (no allOf/if/then; API unsupported).
    Full validation is done locally with action_proposal.v0.1.
    Includes optional "reasoning" for chain-of-thought (SOTA); strip before engine.
    OpenAI structured outputs require additionalProperties: false on every object;
    args therefore lists optional properties for known action args.
    """
    # Args object: OpenAI strict mode requires additionalProperties: false and required
    # to list all properties. Use type ["string", "null"] so model can omit via null.
    _arg_prop = {"type": ["string", "null"]}
    args_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "device_id",
            "work_id",
            "priority_class",
            "result_id",
            "from_zone",
            "to_zone",
            "door_id",
            "specimen_id",
        ],
        "properties": {
            "device_id": _arg_prop,
            "work_id": _arg_prop,
            "priority_class": _arg_prop,
            "result_id": _arg_prop,
            "from_zone": _arg_prop,
            "to_zone": _arg_prop,
            "door_id": _arg_prop,
            "specimen_id": _arg_prop,
        },
    }
    return {
        "type": "object",
        "properties": {
            "action_type": {"type": "string", "minLength": 1},
            "args": args_schema,
            "reason_code": {"anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}]},
            "token_refs": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
            "rationale": {"type": "string", "minLength": 1},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "safety_notes": {"type": "string"},
            "reasoning": {
                "type": "string",
                "description": "Optional step-by-step reasoning (chain-of-thought) before the action choice.",
            },
        },
        "required": [
            "action_type",
            "args",
            "reason_code",
            "token_refs",
            "rationale",
            "confidence",
            "safety_notes",
            "reasoning",
        ],
        "additionalProperties": False,
    }


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


def _load_model_pricing(repo_root: Any | None = None) -> dict[str, Any]:
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
    repo_root: Any | None = None,
) -> float | None:
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
        return (total_prompt_tokens / 1_000_000.0) * float(inp) + (total_completion_tokens / 1_000_000.0) * float(out)
    except (TypeError, ValueError):
        return None


def _build_system_plus_developer(use_chain_of_thought: bool = False) -> str:
    """Prompt Pack v1: system + developer; optional CoT appendix when use_chain_of_thought."""
    from labtrust_gym.baselines.llm.prompts import (
        DEVELOPER_PROMPT_ACTION_PROPOSAL,
        SYSTEM_PROMPT_ACTION_PROPOSAL,
        SYSTEM_PROMPT_CHAIN_OF_THOUGHT_APPENDIX,
    )

    out = SYSTEM_PROMPT_ACTION_PROPOSAL + "\n\n" + DEVELOPER_PROMPT_ACTION_PROPOSAL
    if use_chain_of_thought:
        out = out + SYSTEM_PROMPT_CHAIN_OF_THOUGHT_APPENDIX
    return out


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
    - Capability flags: supports_structured_outputs=True, supports_tool_calls=True
      (read-only tools when use_tools; guardrails in tool_proxy).
    """

    supports_structured_outputs = True
    supports_tool_calls = True

    MAX_TOOL_ROUNDS = 3

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
        timeout_s: int | None = None,
        retries: int | None = None,
        trace_collector: Any = None,
    ) -> None:
        key, mod, fall_list, to, ret = _get_config()
        self._api_key = (api_key or key).strip()
        self._model = (model or mod).strip() or "gpt-4o-mini"
        if fallback_model is not None:
            self._fallback_models = [fallback_model] if fallback_model != self._model else []
        else:
            self._fallback_models = [m for m in fall_list if m != self._model]
        self._timeout_s = timeout_s if timeout_s is not None else to
        self._retries = retries if retries is not None else ret
        self._schema = _action_proposal_schema_for_api()
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
        """True if API key is set (backend can be used)."""
        return bool(self._api_key)

    @property
    def last_error_code(self) -> str | None:
        """Set after propose_action/generate on refusal/timeout/error."""
        return self._last_error_code

    @property
    def last_metrics(self) -> dict[str, Any]:
        """model_id, backend_id, latency_ms, prompt_sha256, response_sha256."""
        return dict(self._last_metrics)

    def get_aggregate_metrics(self) -> dict[str, Any]:
        """
        Aggregate stats over all generate/propose_action calls since init or last reset.
        Returns: backend_id, model_id, total_calls, error_count, error_rate, sum_latency_ms,
        mean_latency_ms, p50_latency_ms, p95_latency_ms, total_tokens, tokens_per_step,
        estimated_cost_usd (when model_pricing available).
        """
        rate = self._error_count / self._total_calls if self._total_calls > 0 else 0.0
        mean_ms = self._sum_latency_ms / self._total_calls if self._total_calls > 0 else None
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
        }
        cost = _estimated_cost_usd(
            self._model,
            self._total_prompt_tokens,
            self._total_completion_tokens,
        )
        if cost is not None:
            out["estimated_cost_usd"] = round(cost, 6)
        return out

    def reset_aggregate_metrics(self) -> None:
        """Reset aggregate counters for per-episode tracking. Call at episode start."""
        self._total_calls = 0
        self._error_count = 0
        self._sum_latency_ms = 0.0
        self._total_tokens = 0
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._latency_ms_list = []

    def snapshot_aggregate_metrics(self) -> dict[str, Any]:
        """
        Return current aggregate metrics (e.g. for this episode) without resetting.
        Includes total_tokens, estimated_cost_usd, total_calls, error_count, mean_latency_ms.
        """
        out = self.get_aggregate_metrics()
        return {k: v for k, v in out.items() if v is not None}

    def propose_action(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Propose one action from context. Returns ActionProposal dict or NOOP on error.

        context: partner_id, policy_fingerprint, now_ts_s, timing_mode,
        state_summary, allowed_actions, active_tokens, recent_violations,
        enforcement_state. Optional: conversation_history (list of {role, content})
        for multi-turn; use_tools (bool) and tools from tool_proxy.get_read_only_tool_definitions_for_llm()
        for read-only function calling (guardrails: tools cannot override RBAC).
        """
        from labtrust_gym.pipeline import check_network_allowed

        check_network_allowed()
        self._last_error_code = None
        self._last_metrics = {}
        self._total_calls += 1
        tracer = None
        try:
            from labtrust_gym.baselines.llm.llm_tracer import get_llm_tracer

            tracer = get_llm_tracer()
        except Exception:
            pass
        if tracer is not None:
            tracer.start_span("propose_action")
            tracer.set_attribute("model_id", self._model)
            tracer.set_attribute("backend_id", BACKEND_ID)
            if context.get("agent_id") is not None:
                tracer.set_attribute("agent_id", str(context["agent_id"]))
        if not self._api_key:
            if tracer is not None:
                tracer.end_span("error", "OPENAI_API_KEY not set")
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
        use_few_shot = context.get("use_few_shot") or (
            os.environ.get("LABTRUST_LLM_FEW_SHOT", "").strip().lower() in ("1", "true", "yes")
        )
        use_rag = context.get("use_rag") or (
            os.environ.get("LABTRUST_LLM_RAG", "").strip().lower() in ("1", "true", "yes")
        )
        use_chain_of_thought = context.get("use_chain_of_thought") or (
            os.environ.get("LABTRUST_LLM_CHAIN_OF_THOUGHT", "").strip().lower() in ("1", "true", "yes")
        )
        use_tools = context.get("use_tools") or (
            os.environ.get("LABTRUST_LLM_TOOLS", "").strip().lower() in ("1", "true", "yes")
        )
        few_shot_block = ""
        if use_few_shot:
            try:
                from labtrust_gym.baselines.llm.few_shot import get_few_shot_block_from_policy

                few_shot_block = get_few_shot_block_from_policy()
            except Exception:
                pass
        rag_excerpts = ""
        if use_rag:
            try:
                from labtrust_gym.baselines.llm.policy_rag import build_rag_context

                rag_excerpts = build_rag_context(
                    state_summary=state_summary,
                    allowed_actions=allowed_actions,
                    top_k=3,
                )
            except Exception:
                pass
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
            few_shot_block=few_shot_block,
            rag_excerpts=rag_excerpts,
        )
        history = context.get("conversation_history")
        if isinstance(history, list) and history:
            turns = [
                {"role": str(t.get("role", "user")), "content": str(t.get("content", ""))}
                for t in history[-MAX_CONVERSATION_HISTORY_TURNS * 2 :]
                if t.get("role") in ("user", "assistant") and t.get("content") is not None
            ]
        else:
            turns = []
        system_content = _build_system_plus_developer(use_chain_of_thought=use_chain_of_thought)
        messages = [
            {"role": "system", "content": system_content},
            *turns,
            {"role": "user", "content": user_content},
        ]
        prompt_sha256 = _sha256(json.dumps(messages, sort_keys=True))
        cache_enabled = not use_tools
        request_cache = None
        if cache_enabled:
            _, request_cache = self._get_request_cache()
        if cache_enabled and request_cache is not None:
            cached = request_cache.get(prompt_sha256)
            if cached is not None:
                raw, usage = cached
                self._total_tokens += usage.get("total_tokens", 0)
                self._total_prompt_tokens += usage.get("prompt_tokens", 0)
                self._total_completion_tokens += usage.get("completion_tokens", 0)
                self._last_metrics = {
                    "model_id": self._model,
                    "backend_id": BACKEND_ID,
                    "latency_ms": 0,
                    "prompt_sha256": prompt_sha256,
                    "response_sha256": _sha256(raw),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                    "request_cache_hit": True,
                    "last_user_content": user_content,
                    "last_assistant_content": raw,
                }
                try:
                    out = json.loads(raw)
                except json.JSONDecodeError:
                    out = dict(NOOP_ACTION_V01)
                if isinstance(out, dict):
                    if tracer is not None:
                        tracer.set_attribute("request_cache_hit", True)
                        tracer.end_span("ok")
                    out_engine = {k: v for k, v in out.items() if k != "reasoning"}
                    return out_engine
                if tracer is not None:
                    tracer.end_span("error", "cached response invalid")
                return dict(NOOP_ACTION_V01)
        start = time.perf_counter()
        try:
            if use_tools:
                policy_summary = context.get("policy_summary") or {}
                tool_context = {
                    "allowed_actions": allowed_actions,
                    "restricted_zones": context.get("restricted_zones") or policy_summary.get("restricted_zones") or [],
                    "state_summary": state_summary,
                    "policy_summary": policy_summary,
                }
                raw, usage = self._call_api_with_tools(messages, tool_context)
            else:
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
            if tracer is not None:
                tracer.end_span("error", str(e)[:200])
            return dict(NOOP_ACTION_V01)
        latency_ms = (time.perf_counter() - start) * 1000
        self._sum_latency_ms += latency_ms
        self._latency_ms_list.append(latency_ms)
        self._total_tokens += usage.get("total_tokens", 0)
        self._total_prompt_tokens += usage.get("prompt_tokens", 0)
        self._total_completion_tokens += usage.get("completion_tokens", 0)
        response_sha256 = _sha256(raw)
        if tracer is not None:
            tracer.set_attribute("latency_ms", round(latency_ms, 2))
            tracer.set_attribute("prompt_tokens", usage.get("prompt_tokens", 0))
            tracer.set_attribute("completion_tokens", usage.get("completion_tokens", 0))
            cost = _estimated_cost_usd(
                self._model,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )
            if cost is not None:
                tracer.set_attribute("estimated_cost_usd", round(cost, 6))
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            out = None
        if out is None or not isinstance(out, dict):
            retry_ok = False
            try:
                from labtrust_gym.baselines.llm.structured_output_retry import (
                    parse_and_normalize_raw,
                    retry_free_form_enabled,
                )

                if retry_free_form_enabled():
                    start_retry = time.perf_counter()
                    raw2, usage2 = self._call_api(messages, structured_output=False)
                    latency_retry_ms = (time.perf_counter() - start_retry) * 1000
                    out = parse_and_normalize_raw(raw2)
                    if isinstance(out, dict):
                        retry_ok = True
                        self._sum_latency_ms += latency_retry_ms
                        self._total_tokens += usage2.get("total_tokens", 0)
                        self._total_prompt_tokens += usage2.get("prompt_tokens", 0)
                        self._total_completion_tokens += usage2.get("completion_tokens", 0)
                        usage = usage2
                        latency_ms += latency_retry_ms
                        response_sha256 = _sha256(raw2)
                        raw = raw2
            except Exception:
                pass
            if not retry_ok:
                if tracer is not None:
                    tracer.end_span("error", "parse failed, retry disabled or failed")
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
        if tracer is not None:
            tracer.end_span("ok")
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
            "last_user_content": user_content,
            "last_assistant_content": raw,
        }
        if usage.get("cached_tokens") is not None:
            self._last_metrics["cached_tokens"] = usage["cached_tokens"]
        if self._trace_collector is not None:
            usage_with_latency = dict(usage)
            usage_with_latency["latency_ms"] = round(latency_ms, 2)
            self._trace_collector.record(messages, raw, prompt_sha256, usage_with_latency)
        cache_enabled_after, request_cache_after = self._get_request_cache()
        if cache_enabled_after and request_cache_after is not None:
            request_cache_after.set(prompt_sha256, raw, usage)
        # Strip optional SOTA fields not in engine contract (reasoning for CoT).
        out_engine = {k: v for k, v in out.items() if k != "reasoning"}
        # Strip null args (OpenAI strict schema requires all keys; we use null for omitted).
        if isinstance(out_engine.get("args"), dict):
            out_engine["args"] = {k: v for k, v in out_engine["args"].items() if v is not None}
        return out_engine

    def _get_request_cache(self) -> tuple[bool, Any]:
        """Return (enabled, cache or None). Lazy import to avoid circular deps."""
        try:
            from labtrust_gym.baselines.llm.request_cache import get_request_cache

            return get_request_cache()
        except Exception:
            return (False, None)

    def _call_api_with_tools(
        self,
        messages: list[dict[str, Any]],
        tool_context: dict[str, Any],
    ) -> tuple[str, UsageDict]:
        """
        Call API with read-only tools; handle tool_calls and optional follow-up.
        Returns (content, usage). Guardrails: only tools from tool_proxy allowlist.
        """
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError("openai not installed; pip install -e '.[llm_openai]'") from e
        from labtrust_gym.baselines.llm.tool_proxy import (
            execute_read_only_tool,
            get_read_only_tool_definitions_for_llm,
        )

        client = OpenAI(api_key=self._api_key)
        model = self._model.strip() or "gpt-4o-mini"
        tool_defs = get_read_only_tool_definitions_for_llm()
        allowed_tool_names = {f["function"]["name"] for f in tool_defs}
        current = list(messages)
        total_usage: UsageDict = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        for round_idx in range(self.MAX_TOOL_ROUNDS):
            create_kwargs: dict[str, Any] = {
                "model": model,
                "messages": cast(Any, current),
                "tools": tool_defs,
                "tool_choice": "auto",
                "timeout": float(self._timeout_s),
            }
            resp = client.chat.completions.create(**create_kwargs)
            choice = resp.choices[0] if resp.choices else None
            if not choice or not getattr(choice, "message", None):
                raise RuntimeError("Empty response in tool round")
            msg = choice.message
            usage = _usage_from_response(resp)
            total_usage["prompt_tokens"] = total_usage.get("prompt_tokens", 0) + usage.get("prompt_tokens", 0)
            total_usage["completion_tokens"] = total_usage.get("completion_tokens", 0) + usage.get(
                "completion_tokens", 0
            )
            total_usage["total_tokens"] = total_usage.get("total_tokens", 0) + usage.get("total_tokens", 0)
            tool_calls = getattr(msg, "tool_calls", None) or []
            content = (getattr(msg, "content", None) or "").strip()
            if not tool_calls:
                if content:
                    return (content, total_usage)
                raise RuntimeError("No content and no tool_calls in tool round")
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": content or None}
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": getattr(tc, "id", ""),
                        "type": "function",
                        "function": {
                            "name": getattr(getattr(tc, "function", None), "name", ""),
                            "arguments": getattr(getattr(tc, "function", None), "arguments", "{}"),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            current.append(assistant_msg)
            for tc in msg.tool_calls:
                name = getattr(getattr(tc, "function", None), "name", "")
                _args_str = getattr(getattr(tc, "function", None), "arguments", "{}") or "{}"
                if name not in allowed_tool_names:
                    current.append(
                        {
                            "role": "tool",
                            "tool_call_id": getattr(tc, "id", ""),
                            "content": json.dumps({"error": "tool not allowed"}),
                        }
                    )
                    continue
                try:
                    result = execute_read_only_tool(name, tool_context)
                except Exception as e:
                    result = json.dumps({"error": str(e)[:200]})
                current.append(
                    {
                        "role": "tool",
                        "tool_call_id": getattr(tc, "id", ""),
                        "content": result,
                    }
                )
        final_user = {
            "role": "user",
            "content": "Based on the tool results above, output a single ActionProposal JSON.",
        }
        current.append(final_user)
        final_content, final_usage = self._call_api(current, structured_output=True)
        total_usage["prompt_tokens"] = total_usage.get("prompt_tokens", 0) + final_usage.get("prompt_tokens", 0)
        total_usage["completion_tokens"] = total_usage.get("completion_tokens", 0) + final_usage.get(
            "completion_tokens", 0
        )
        total_usage["total_tokens"] = total_usage.get("total_tokens", 0) + final_usage.get("total_tokens", 0)
        return (final_content, total_usage)

    def _call_api(
        self,
        messages: list[dict[str, str]],
        model_override: str | None = None,
        structured_output: bool = True,
    ) -> tuple[str, UsageDict]:
        """
        Call OpenAI Chat Completions. Returns (content, usage).
        When structured_output=True use JSON schema; when False use free-form (for retry).
        """
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError("openai not installed; pip install -e '.[llm_openai]'") from e

        client = OpenAI(api_key=self._api_key)
        model = (model_override or self._model).strip() or self._model
        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": cast(Any, messages),
            "timeout": float(self._timeout_s),
        }
        if structured_output:
            create_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "action_proposal_v01",
                    "strict": True,
                    "schema": self._schema,
                },
            }
        prompt_cache_key = (os.environ.get("LABTRUST_LLM_PROMPT_CACHE_KEY") or "").strip()
        if prompt_cache_key:
            create_kwargs["prompt_cache_key"] = prompt_cache_key
        prompt_cache_retention = (os.environ.get("LABTRUST_LLM_PROMPT_CACHE_RETENTION") or "").strip().lower()
        if prompt_cache_retention in ("24h", "in_memory", "in-memory"):
            create_kwargs["prompt_cache_retention"] = "24h" if prompt_cache_retention == "24h" else "in_memory"
        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self._retries:
            if attempt > 0:
                backoff_s = min(2**attempt, MAX_BACKOFF_S)
                time.sleep(backoff_s)
            try:
                resp = client.chat.completions.create(**create_kwargs)
            except Exception as e:
                last_exc = e
                if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                    self._last_error_code = LLM_TIMEOUT
                attempt += 1
                if attempt > self._retries:
                    if model_override is None and self._fallback_models:
                        for fb in self._fallback_models:
                            try:
                                return self._call_api(messages, model_override=fb)
                            except Exception:
                                continue
                    raise last_exc
                continue
            choice = resp.choices[0] if resp.choices else None
            if not choice or not getattr(choice, "message", None):
                last_exc = RuntimeError("Empty response")
                attempt += 1
                if attempt > self._retries:
                    if model_override is None and self._fallback_models:
                        for fb in self._fallback_models:
                            try:
                                return self._call_api(messages, model_override=fb)
                            except Exception:
                                continue
                    raise last_exc
                continue
            msg = choice.message
            if getattr(msg, "refusal", None):
                self._last_error_code = LLM_REFUSED
                attempt += 1
                if attempt > self._retries:
                    if model_override is None and self._fallback_models:
                        for fb in self._fallback_models:
                            try:
                                return self._call_api(messages, model_override=fb)
                            except Exception:
                                continue
                    raise RuntimeError(f"Refusal: {msg.refusal}")
                last_exc = RuntimeError(f"Refusal: {msg.refusal}")
                continue
            content = getattr(msg, "content", None) or ""
            if not content or not content.strip():
                last_exc = RuntimeError("Empty content")
                attempt += 1
                if attempt > self._retries:
                    if model_override is None and self._fallback_models:
                        for fb in self._fallback_models:
                            try:
                                return self._call_api(messages, model_override=fb)
                            except Exception:
                                continue
                    raise last_exc
                continue
            usage = _usage_from_response(resp)
            return (content.strip(), usage)
        raise last_exc or RuntimeError("No response")

    def generate(self, messages: list[dict[str, str]]) -> str:
        """LLMBackend protocol: return raw JSON string. Uses messages as-is for API."""
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
            self._last_error_code = getattr(self, "_last_error_code", None) or LLM_PROVIDER_ERROR
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

    def healthcheck(self) -> dict[str, Any]:
        """
        One minimal request; returns dict with ok, model_id, latency_ms, usage, error.
        Caller must ensure pipeline_mode=llm_live and allow_network.
        """
        from labtrust_gym.pipeline import check_network_allowed

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


def _usage_from_response(resp: Any) -> UsageDict:
    """
    Extract prompt_tokens, completion_tokens, total_tokens from OpenAI response.
    Includes cached_tokens when present (prompt caching).
    """
    u = getattr(resp, "usage", None)
    if u is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    out: UsageDict = {
        "prompt_tokens": int(getattr(u, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(u, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(u, "total_tokens", 0) or 0),
    }
    details = getattr(u, "prompt_tokens_details", None)
    if details is not None and hasattr(details, "cached_tokens"):
        ct = getattr(details, "cached_tokens", None)
        if ct is not None:
            out["cached_tokens"] = int(ct)
    return out
