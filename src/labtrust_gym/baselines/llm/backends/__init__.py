"""
LLM backends: deterministic (in agent.py) and optional live providers.

- ProviderBackend interface is in baselines.llm.provider (no optional deps).
- Per-provider code is behind optional extras: llm_openai (openai_live.py), llm_anthropic (later).
- Engine logic uses ProviderBackend only; add new providers without touching engine.
"""

from __future__ import annotations

from labtrust_gym.baselines.llm.provider import ProviderBackend

__all__ = ["ProviderBackend"]
