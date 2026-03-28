"""
OpenAI-backed agent-driven episode loop: LLM calls step_lab to advance the env.

Implements run_episode(driver) that runs a conversation until driver.is_done()
or max_turns. Tools: step_lab(proposal), get_current_obs(), end_episode().
Does not modify the simulation-centric generate_proposal path.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, cast

from labtrust_gym.benchmarks.agent_driven_driver import (
    END_EPISODE_TOOL_NAME,
    GET_CURRENT_OBS_TOOL_NAME,
    STEP_LAB_TOOL_NAME,
    AgentDrivenDriver,
    agent_driven_tool_definitions,
)
from labtrust_gym.pipeline import check_network_allowed

LOG = logging.getLogger(__name__)

BACKEND_ID = "openai_agent_driven"

DEFAULT_MAX_TURNS = 200


def _run_episode_system_prompt() -> str:
    return (
        "You are the lab controller. Advance the simulation by calling "
        "step_lab(proposal) with a coordination proposal. "
        "Each proposal must have: proposal_id, step_id, method_id, per_agent "
        "(list of {agent_id, action_type, args, reason_code}), comms, meta. "
        "action_type: NOOP, TICK, QUEUE_RUN, MOVE, OPEN_DOOR, START_RUN. "
        "You receive back observations, rewards, terminations, truncations, done. "
        "Call step_lab until done is true or you call end_episode(). "
        "You may call get_current_obs() to read state without stepping."
    )


class OpenAIAgentDrivenBackend:
    """
    Agent-driven backend: run_episode(driver) runs the LLM conversation loop;
    the model calls step_lab (and optionally get_current_obs, end_episode) until driver.is_done().
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: int = 60,
        max_turns: int = DEFAULT_MAX_TURNS,
        *,
        openai_base_url: str | None = None,
        openai_default_headers: dict[str, str] | None = None,
    ) -> None:
        self._api_key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
        self._model = (model or os.environ.get("LABTRUST_OPENAI_MODEL") or "gpt-4o-mini").strip()
        self._timeout_s = max(10, timeout_s)
        self._max_turns = max(1, min(max_turns, 500))
        self._openai_base_url = (openai_base_url or "").strip() or None
        self._openai_default_headers = dict(openai_default_headers) if openai_default_headers else None

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def run_episode(self, driver: AgentDrivenDriver) -> None:
        """Run agent-driven loop until driver.is_done() or max_turns."""
        check_network_allowed()
        if not (self._api_key or "").strip():
            raise ValueError("API key required for agent-driven backend (e.g. OPENAI_API_KEY or provider key).")
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError("openai not installed; pip install -e '.[llm_openai]'") from e
        _ckw: dict[str, Any] = {"api_key": self._api_key}
        if self._openai_base_url:
            _ckw["base_url"] = self._openai_base_url
        if self._openai_default_headers:
            _ckw["default_headers"] = self._openai_default_headers
        client = OpenAI(**_ckw)
        tool_defs = agent_driven_tool_definitions(include_optional=True)
        system_content = _run_episode_system_prompt()
        initial = driver.get_current_obs()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "initial_obs_summary": list(initial.get("observations", {}).keys()),
                        "step_index": initial.get("step_index"),
                        "done": initial.get("done"),
                    },
                    sort_keys=True,
                ),
            },
        ]
        turn = 0
        while not driver.is_done() and turn < self._max_turns:
            turn += 1
            try:
                resp = client.chat.completions.create(
                    model=self._model,
                    messages=cast(Any, messages),
                    tools=tool_defs,
                    tool_choice="auto",
                    timeout=float(self._timeout_s),
                )
            except Exception as e:
                LOG.warning("OpenAI agent_driven turn %s failed: %s", turn, e)
                break
            choice = resp.choices[0] if resp.choices else None
            if not choice or not getattr(choice, "message", None):
                break
            msg = choice.message
            tool_calls = getattr(msg, "tool_calls", None) or []
            content = (getattr(msg, "content", None) or "").strip()
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": content or None,
            }
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": getattr(tc, "id", ""),
                        "type": "function",
                        "function": {
                            "name": getattr(getattr(tc, "function", None), "name", ""),
                            "arguments": (getattr(getattr(tc, "function", None), "arguments", "{}") or "{}"),
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)
            for tc in tool_calls:
                fn = getattr(tc, "function", None)
                name = getattr(fn, "name", "") or ""
                args_str = getattr(fn, "arguments", "{}") or "{}"
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    args = {}
                tid = getattr(tc, "id", "") or ""
                if name == STEP_LAB_TOOL_NAME:
                    proposal = args.get("proposal") if isinstance(args.get("proposal"), dict) else {}
                    result = driver.step_lab(proposal)
                elif name == GET_CURRENT_OBS_TOOL_NAME:
                    result = driver.get_current_obs()
                elif name == END_EPISODE_TOOL_NAME:
                    result = driver.end_episode()
                else:
                    result = {"error": "unknown_tool", "name": name}
                content_str = json.dumps(result) if isinstance(result, dict) else str(result)
                messages.append({"role": "tool", "tool_call_id": tid, "content": content_str})
                if driver.is_done():
                    break
            if not tool_calls and content:
                break
        return
