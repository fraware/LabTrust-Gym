"""
Live Ollama backend (local; no strict JSON schema).

- Reads LABTRUST_LOCAL_LLM_URL, LABTRUST_LOCAL_LLM_MODEL, LABTRUST_LOCAL_LLM_TIMEOUT from env.
- Implements LLMBackend (generate -> str). Agent uses extract_first_json_object + ActionProposal
  validation + repair when supports_structured_outputs=False.
- Per-provider code: no optional extra (uses urllib); optional extra llm_ollama for future deps.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

# NOOP shape for error fallback (ActionProposal v0.1)
NOOP_ACTION_V01: dict[str, Any] = {
    "action_type": "NOOP",
    "args": {},
    "reason_code": None,
    "token_refs": [],
    "rationale": "Ollama backend error fallback.",
    "confidence": 0.0,
    "safety_notes": "",
}

LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"
LLM_TIMEOUT = "LLM_TIMEOUT"

BACKEND_ID = "ollama_live"
LOG = logging.getLogger(__name__)

# Ollama reports tokens but not cost (local/free). estimated_cost_usd remains None.


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (k - lo) * (sorted_vals[hi] - sorted_vals[lo])


def _get_config() -> tuple[str, str, int]:
    """
    Read config from environment. Returns (base_url, model, timeout_s).

    LABTRUST_LOCAL_LLM_URL: base URL (e.g. http://localhost:11434).
    LABTRUST_LOCAL_LLM_MODEL: model name (e.g. llama3.2).
    LABTRUST_LOCAL_LLM_TIMEOUT: timeout in seconds (default 60).
    """
    url = (os.environ.get("LABTRUST_LOCAL_LLM_URL") or "http://localhost:11434").strip()
    if not url.endswith("/"):
        url = url + "/"
    model = (os.environ.get("LABTRUST_LOCAL_LLM_MODEL") or "llama3.2").strip()
    try:
        timeout_s = int(os.environ.get("LABTRUST_LOCAL_LLM_TIMEOUT", "60"))
    except ValueError:
        timeout_s = 60
    if timeout_s <= 0:
        timeout_s = 60
    return (url, model, timeout_s)


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class OllamaLiveBackend:
    """
    Live Ollama backend. Provider cannot enforce JSON schema; agent uses
    JSON-only prompts + extract_first_json_object + ActionProposal validation + repair.

    - Reads LABTRUST_LOCAL_LLM_URL, LABTRUST_LOCAL_LLM_MODEL, LABTRUST_LOCAL_LLM_TIMEOUT.
    - generate(messages) -> str (raw response; agent parses with extract_first_json_object).
    - supports_structured_outputs = False so audit and agent use robust parse + repair.
    """

    supports_structured_outputs = False
    supports_tool_calls = False

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
        self._last_error_code: str | None = None
        self._last_metrics: dict[str, Any] = {}
        self._total_calls: int = 0
        self._error_count: int = 0
        self._sum_latency_ms: float = 0.0
        self._total_tokens: int = 0
        self._latency_ms_list: list[float] = []

    @property
    def is_available(self) -> bool:
        """True if base URL is set (backend can be used)."""
        return bool(self._base_url)

    @property
    def last_error_code(self) -> str | None:
        """Set after generate on timeout/error."""
        return self._last_error_code

    @property
    def last_metrics(self) -> dict[str, Any]:
        """model_id, backend_id, latency_ms, prompt_sha256, response_sha256."""
        return dict(self._last_metrics)

    def get_aggregate_metrics(self) -> dict[str, Any]:
        """
        Aggregate stats over all generate calls since init.
        Returns: backend_id, model_id, total_calls, error_count, error_rate,
        sum_latency_ms, mean_latency_ms, total_tokens, tokens_per_step,
        p50_latency_ms, p95_latency_ms. estimated_cost_usd is None (Ollama is local).
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
        return {
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

    def generate(self, messages: list[dict[str, str]]) -> str:
        """
        Call Ollama /api/chat and return message content as string.

        Agent will use extract_first_json_object + ActionProposal validation + repair.
        On error returns NOOP JSON string.
        """
        from labtrust_gym.pipeline import check_network_allowed

        check_network_allowed()
        self._last_error_code = None
        self._last_metrics = {}
        self._total_calls += 1
        prompt_sha256 = _sha256(json.dumps(messages, sort_keys=True))
        start = time.perf_counter()
        try:
            raw = self._call_api(messages)
        except urllib.error.HTTPError as e:
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
            LOG.debug("Ollama HTTP error: %s", str(e)[:200])
            return json.dumps(NOOP_ACTION_V01, sort_keys=True)
        except urllib.error.URLError as e:
            latency_ms = (time.perf_counter() - start) * 1000
            reason = str(e.reason or "").lower()
            self._last_error_code = LLM_TIMEOUT if "timed out" in reason else LLM_PROVIDER_ERROR
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
            LOG.debug("Ollama URL error: %s", str(e)[:200])
            return json.dumps(NOOP_ACTION_V01, sort_keys=True)
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
            LOG.debug("Ollama backend error: %s", str(e)[:200])
            return json.dumps(NOOP_ACTION_V01, sort_keys=True)
        latency_ms = (time.perf_counter() - start) * 1000
        self._sum_latency_ms += latency_ms
        self._latency_ms_list.append(latency_ms)
        response_sha256 = _sha256(raw)
        self._last_metrics = {
            "model_id": self._model,
            "backend_id": BACKEND_ID,
            "latency_ms": round(latency_ms, 2),
            "prompt_sha256": prompt_sha256,
            "response_sha256": response_sha256,
        }
        return raw

    def _call_api(self, messages: list[dict[str, str]]) -> tuple[str, dict[str, int]]:
        """POST to Ollama /api/chat. Returns (content_str, usage_dict with prompt_tokens, completion_tokens, total_tokens)."""
        payload = {
            "model": self._model,
            "messages": [{"role": m.get("role", "user"), "content": m.get("content", "") or ""} for m in messages],
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._base_url + "api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = data.get("message")
        if not isinstance(msg, dict):
            raise RuntimeError("Ollama response missing message")
        content = msg.get("content")
        if content is None:
            content = "{}"
        prompt_eval = int(data.get("prompt_eval_count", 0) or 0)
        eval_count = int(data.get("eval_count", 0) or 0)
        usage = {
            "prompt_tokens": prompt_eval,
            "completion_tokens": eval_count,
            "total_tokens": prompt_eval + eval_count,
        }
        return (str(content).strip(), usage)

    def healthcheck(self) -> dict[str, Any]:
        """
        One minimal request; returns dict with ok, model_id, latency_ms, usage, error.
        Same contract as openai_live/anthropic_live. Caller must ensure pipeline_mode=llm_live
        and allow_network (e.g. via CLI).
        """
        from labtrust_gym.pipeline import check_network_allowed

        check_network_allowed()
        messages = [
            {
                "role": "user",
                "content": "Return a single JSON object: action_type=NOOP, args={}, reason_code=null, token_refs=[], rationale=Health check, confidence=1.0, safety_notes=.",
            },
        ]
        start = time.perf_counter()
        try:
            raw, usage = self._call_api(messages)
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
        except Exception as e:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "ok": False,
                "model_id": self._model,
                "latency_ms": latency_ms,
                "usage": {},
                "error": str(e)[:400],
            }
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("action_type") == "NOOP":
                return {
                    "ok": True,
                    "model_id": self._model,
                    "latency_ms": latency_ms,
                    "usage": usage,
                    "error": None,
                }
        except json.JSONDecodeError:
            pass
        return {
            "ok": False,
            "model_id": self._model,
            "latency_ms": latency_ms,
            "usage": usage,
            "error": "Response did not match expected NOOP schema",
        }
