"""LLM agent interface: offline-safe, deterministic by default."""

from __future__ import annotations

from labtrust_gym.baselines.llm.action_proposal import (
    load_action_proposal_schema,
    validate_action_proposal_dict,
)
from labtrust_gym.baselines.llm.agent import (
    DeterministicConstrainedBackend,
    FixtureBackend,
    LLMAgent,
    LLMAgentWithShield,
    LLMBackend,
    MockDeterministicBackend,
    MockDeterministicBackendV2,
)
from labtrust_gym.baselines.llm.decoder import decode_constrained
from labtrust_gym.baselines.llm.exceptions import (
    AuthError,
    FixtureMissingError,
    LLMBackendError,
    ProviderUnavailable,
    RateLimitError,
)
from labtrust_gym.baselines.llm.provider import (
    ProviderBackend,
    supports_structured_outputs,
    supports_tool_calls,
)

__all__ = [
    "AuthError",
    "FixtureMissingError",
    "LLMBackend",
    "LLMAgent",
    "LLMAgentWithShield",
    "DeterministicConstrainedBackend",
    "FixtureBackend",
    "MockDeterministicBackend",
    "MockDeterministicBackendV2",
    "ProviderBackend",
    "decode_constrained",
    "load_action_proposal_schema",
    "supports_structured_outputs",
    "supports_tool_calls",
    "validate_action_proposal_dict",
]
