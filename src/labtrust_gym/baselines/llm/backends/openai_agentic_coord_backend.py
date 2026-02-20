"""
OpenAI-backed agentic coordinator proposal backend: tool_calls / tool_results protocol.

Used by llm_central_planner_agentic when llm_backend=openai_live. Supports
generate_proposal(..., tool_results=<list>); returns (proposal_dict, meta) with
optional meta["tool_calls"] so the coordinator can run tools and call again.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, cast

from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
    REASON_OPENAI_API_KEY_MISSING,
    _estimated_cost_usd,
    require_openai_api_key,
)
from labtrust_gym.security.secret_scrubber import scrub_dict_for_log, scrub_secrets

LOG = logging.getLogger(__name__)

BACKEND_ID = "openai_live_agentic_coord"


def _coord_tool_definitions() -> list[dict[str, Any]]:
    """OpenAI tool definitions for coordinator tools (query_queue_state, get_detector_recommendation)."""
    return [
        {
            "type": "function",
            "function": {
                "name": "query_queue_state",
                "description": "Return a compact queue state summary for each agent (queue_by_device, queue_has_head).",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_detector_recommendation",
                "description": "Get a detector recommendation (enforcement_action, rationale). Stub in this backend.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
    ]


def _fallback_proposal(agent_ids: list[str], step_id: int, method_id: str) -> dict[str, Any]:
    return {
        "proposal_id": f"fallback-{step_id}",
        "step_id": step_id,
        "method_id": method_id,
        "horizon_steps": 1,
        "per_agent": [
            {"agent_id": aid, "action_type": "NOOP", "args": {}, "reason_code": "COORD_BACKEND_ERROR"}
            for aid in agent_ids
        ],
        "comms": [],
        "meta": {},
    }


def _parse_proposal_from_content(
    content: str,
    agent_ids: list[str],
    step_id: int,
    method_id: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Parse JSON content as coordination proposal. Return (proposal_dict, None) if valid,
    else (None, error_message).
    """
    content = (content or "").strip()
    if not content:
        return None, "Empty content"
    try:
        proposal = json.loads(content)
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"
    if not isinstance(proposal, dict):
        return None, "Response is not a JSON object"
    per_agent = proposal.get("per_agent")
    if not isinstance(per_agent, list) or len(per_agent) == 0:
        return None, "Missing or empty per_agent"
    for pa in per_agent:
        if not isinstance(pa, dict) or not pa.get("agent_id") or not pa.get("action_type"):
            return None, "per_agent entry missing agent_id or action_type"
    proposal.setdefault("proposal_id", f"agentic-{step_id}")
    proposal.setdefault("step_id", step_id)
    proposal.setdefault("method_id", method_id)
    proposal.setdefault("horizon_steps", 1)
    proposal.setdefault("comms", [])
    if "meta" not in proposal or not isinstance(proposal.get("meta"), dict):
        proposal["meta"] = {}
    return proposal, None


class OpenAIAgenticProposalBackend:
    """
    Agentic coordinator proposal backend: Chat Completions with tools.
    Implements generate_proposal(..., tool_results=<list>); returns (proposal_dict, meta)
    with optional meta["tool_calls"] (list of {"name", "args"}) for the coordinator to run.
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
        self._seed = 0
        self._step_id: int | None = None
        self._last_assistant_msg: dict[str, Any] | None = None
        self._last_tool_call_ids: list[str] = []
        self._last_tool_calls_normalized: list[dict[str, Any]] = []
        self._total_calls = 0
        self._error_count = 0
        self._sum_latency_ms = 0.0
        self._total_tokens_in = 0
        self._total_tokens_out = 0
        self._last_metrics: dict[str, Any] = {}

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    @property
    def last_metrics(self) -> dict[str, Any]:
        return dict(self._last_metrics)

    def reset(self, seed: int) -> None:
        self._seed = seed
        self._step_id = None
        self._last_assistant_msg = None
        self._last_tool_call_ids = []
        self._last_tool_calls_normalized = []

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        allowed_actions: list[str],
        step_id: int,
        method_id: str,
        *,
        tool_results: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        from labtrust_gym.pipeline import check_network_allowed

        check_network_allowed()

        self._total_calls += 1
        agent_ids = [p.get("agent_id") for p in state_digest.get("per_agent") or []]
        if not agent_ids:
            agent_ids = ["ops_0"]
        fallback = _fallback_proposal(agent_ids, step_id, method_id)
        fallback_meta: dict[str, Any] = {
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
            return (fallback, fallback_meta)

        tracer = None
        try:
            from labtrust_gym.baselines.llm.llm_tracer import get_llm_tracer
            tracer = get_llm_tracer()
        except Exception:
            pass
        if tracer is not None:
            tracer.start_span("coord_agentic")
            tracer.set_attribute("backend_id", BACKEND_ID)
            tracer.set_attribute("model_id", self._model)

        tool_results = tool_results or []
        if step_id != self._step_id:
            self._step_id = step_id
            self._last_assistant_msg = None
            self._last_tool_call_ids = []
            self._last_tool_calls_normalized = []

        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai not installed; pip install -e '.[llm_openai]'"
            ) from e

        client = OpenAI(api_key=self._api_key)
        model = self._model.strip() or "gpt-4o-mini"
        tool_defs = _coord_tool_definitions()

        user_content = json.dumps(
            {
                "state_digest": state_digest,
                "allowed_actions": allowed_actions,
                "step_id": step_id,
                "method_id": method_id,
            },
            sort_keys=True,
        )
        system_content = (
            "You are a coordination planner. You may call tools to query queue state or detector recommendations. "
            "When you have enough information, respond with a single JSON object that is a coordination proposal: "
            '{"proposal_id": "...", "step_id": <int>, "method_id": "...", "horizon_steps": 1, "per_agent": [{"agent_id": "...", "action_type": "NOOP|TICK|QUEUE_RUN|MOVE|OPEN_DOOR|START_RUN", "args": {}, "reason_code": "..."}], "comms": []}. '
            "No commentary outside the JSON when producing the final proposal."
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]
        if tool_results and self._last_assistant_msg is not None:
            messages.append(self._last_assistant_msg)
            for i, tr in enumerate(tool_results):
                tc_id = self._last_tool_call_ids[i] if i < len(self._last_tool_call_ids) else f"tc_{i}"
                result = tr.get("result") if isinstance(tr.get("result"), dict) else tr
                content = json.dumps(result) if isinstance(result, dict) else json.dumps(tr)
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": content})

        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                start = time.perf_counter()
                resp = client.chat.completions.create(
                    model=model,
                    messages=cast(Any, messages),
                    tools=tool_defs,
                    tool_choice="auto",
                    timeout=float(self._timeout_s),
                )
                latency_ms = (time.perf_counter() - start) * 1000
                choice = resp.choices[0] if resp.choices else None
                if not choice or not getattr(choice, "message", None):
                    last_exc = RuntimeError("Empty response")
                    if attempt >= self._retries:
                        break
                    continue
                msg = choice.message
                usage = getattr(resp, "usage", None)
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                cost = _estimated_cost_usd(
                    model, prompt_tokens, completion_tokens, self._repo_root
                )
                meta: dict[str, Any] = {
                    "backend_id": BACKEND_ID,
                    "model_id": model,
                    "latency_ms": round(latency_ms, 2),
                    "tokens_in": prompt_tokens,
                    "tokens_out": completion_tokens,
                    "estimated_cost_usd": round(cost, 6) if cost is not None else None,
                }
                self._sum_latency_ms += latency_ms
                self._total_tokens_in += prompt_tokens
                self._total_tokens_out += completion_tokens
                self._last_metrics = dict(meta)

                tool_calls = getattr(msg, "tool_calls", None) or []
                content = (getattr(msg, "content", None) or "").strip()

                if tool_calls:
                    normalized: list[dict[str, Any]] = []
                    ids: list[str] = []
                    for tc in tool_calls:
                        tid = getattr(tc, "id", "") or ""
                        fn = getattr(tc, "function", None)
                        name = getattr(fn, "name", "") or ""
                        args_str = getattr(fn, "arguments", "{}") or "{}"
                        try:
                            args = json.loads(args_str) if args_str else {}
                        except json.JSONDecodeError:
                            args = {}
                        normalized.append({"name": name, "args": args})
                        ids.append(tid)
                    assistant_msg = {
                        "role": "assistant",
                        "content": content or None,
                        "tool_calls": [
                            {
                                "id": getattr(tc, "id", ""),
                                "type": "function",
                                "function": {
                                    "name": getattr(getattr(tc, "function", None), "name", ""),
                                    "arguments": getattr(
                                        getattr(tc, "function", None), "arguments", "{}"
                                    ) or "{}",
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                    self._last_assistant_msg = assistant_msg
                    self._last_tool_call_ids = ids
                    self._last_tool_calls_normalized = normalized
                    meta["tool_calls"] = normalized
                    if tracer is not None:
                        tracer.set_attribute("latency_ms", meta.get("latency_ms"))
                        tracer.set_attribute("prompt_tokens", meta.get("tokens_in", 0))
                        tracer.set_attribute("completion_tokens", meta.get("tokens_out", 0))
                        if meta.get("estimated_cost_usd") is not None:
                            tracer.set_attribute("estimated_cost_usd", meta["estimated_cost_usd"])
                        tracer.end_span()
                    return (fallback, meta)

                if content:
                    proposal, err = _parse_proposal_from_content(
                        content, agent_ids, step_id, method_id
                    )
                    if proposal is not None:
                        self._last_assistant_msg = None
                        self._last_tool_call_ids = []
                        self._last_tool_calls_normalized = []
                        if "meta" not in proposal or not isinstance(proposal.get("meta"), dict):
                            proposal["meta"] = {}
                        proposal["meta"].update(
                            {k: v for k, v in meta.items() if k != "tool_calls"}
                        )
                        if tracer is not None:
                            tracer.set_attribute("latency_ms", meta.get("latency_ms"))
                            tracer.set_attribute("prompt_tokens", meta.get("tokens_in", 0))
                            tracer.set_attribute("completion_tokens", meta.get("tokens_out", 0))
                            if meta.get("estimated_cost_usd") is not None:
                                tracer.set_attribute("estimated_cost_usd", meta["estimated_cost_usd"])
                            tracer.end_span()
                        return (proposal, meta)
                    LOG.debug("Agentic coord parse error: %s", scrub_secrets(err or "")[:200])
                last_exc = RuntimeError(err if content else "No content and no tool_calls")
            except Exception as e:
                last_exc = e
                if attempt >= self._retries:
                    break
                continue

        self._error_count += 1
        self._last_metrics = {
            "backend_id": BACKEND_ID,
            "model_id": self._model,
            "error_code": str(last_exc)[:200] if last_exc else "unknown",
        }
        if tracer is not None:
            tracer.set_attribute("latency_ms", 0)
            tracer.end_span("error", str(last_exc)[:200] if last_exc else "unknown")
        LOG.debug("Agentic coord API error: %s", scrub_secrets(str(last_exc)[:200]))
        return (fallback, fallback_meta)

    def get_aggregate_metrics(self) -> dict[str, Any]:
        n = self._total_calls
        rate = self._error_count / n if n > 0 else 0.0
        mean_ms = self._sum_latency_ms / n if n > 0 else None
        total_tok = self._total_tokens_in + self._total_tokens_out
        tokens_per_step = round(total_tok / n, 2) if n > 0 and total_tok else None
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
            "total_tokens": total_tok,
            "tokens_per_step": tokens_per_step,
            "estimated_cost_usd": round(cost, 6) if cost is not None else None,
        }
