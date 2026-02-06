"""
Provider-neutral live LLM interface.

- ProviderBackend: protocol for backends that return ActionProposal dicts.
- Capability flags: supports_structured_outputs, supports_tool_calls (set by each backend).
- Engine logic depends only on this interface; per-provider code lives behind
  optional extras (llm_openai, llm_anthropic) and implements ProviderBackend
  + LLMBackend (generate) for agent use.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ProviderBackend(Protocol):
    """
    Protocol for live LLM backends that propose actions as ActionProposal dicts.

    Implementations live behind optional extras (e.g. llm_openai, llm_anthropic)
    so the engine and agent do not depend on any specific provider.
    """

    def propose_action(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Propose one action from context. Returns ActionProposal dict (or NOOP on error).

        context: partner_id, policy_fingerprint, now_ts_s, timing_mode, state_summary,
        allowed_actions, active_tokens, recent_violations, enforcement_state.
        """
        ...

    # Capability flags (optional attributes; default False if missing).
    # Backends should set these so the agent/runner can prefer structured output.
    # supports_structured_outputs: bool  - provider natively returns schema output
    # supports_tool_calls: bool          - provider supports tool/function calling


def supports_structured_outputs(backend: Any) -> bool:
    """True if backend natively returns schema-conforming output (best quality)."""
    return getattr(backend, "supports_structured_outputs", False)


def supports_tool_calls(backend: Any) -> bool:
    """True if backend supports tool/function calling."""
    return getattr(backend, "supports_tool_calls", False)
