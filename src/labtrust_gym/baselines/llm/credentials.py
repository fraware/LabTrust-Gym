"""
Central credential resolution for LLM backends.

Single place that loads .env from repo root, validates required API keys
for the chosen backend, and returns credentials for injection into backend
constructors. Call resolve_credentials() before creating any live backend.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _ensure_dotenv_loaded(repo_root: Path | None) -> None:
    """Load .env from repo_root if set and file exists. Idempotent."""
    if repo_root is None:
        return
    env_path = Path(repo_root) / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except ImportError:
        pass


def _require_openai_api_key() -> str:
    """Return OPENAI_API_KEY if set; raise ValueError if not."""
    key = (os.environ.get("OPENAI_API_KEY") or "").strip().strip('"').strip("'")
    if not key:
        raise ValueError(
            "OPENAI_API_KEY_MISSING: OPENAI_API_KEY must be set when using "
            "--llm-backend openai_live/openai_responses/openai_hosted. "
            "Set it in .env in the repo root (copy .env.example to .env), or export OPENAI_API_KEY in your shell."
        )
    return key


def _require_anthropic_api_key() -> str:
    """Return ANTHROPIC_API_KEY if set; raise ValueError if not."""
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip().strip('"').strip("'")
    if not key:
        raise ValueError(
            "ANTHROPIC_API_KEY_MISSING: ANTHROPIC_API_KEY must be set when using "
            "--llm-backend anthropic_live. Set the env var or use another backend."
        )
    return key


def _require_prime_intellect_api_key() -> str:
    """Return PRIME_INTELLECT_API_KEY or PRIME_API_KEY; raise ValueError if not."""
    key = (
        (os.environ.get("PRIME_INTELLECT_API_KEY") or os.environ.get("PRIME_API_KEY") or "")
        .strip()
        .strip('"')
        .strip("'")
    )
    if not key:
        raise ValueError(
            "PRIME_INTELLECT_API_KEY_MISSING: PRIME_INTELLECT_API_KEY (or PRIME_API_KEY) must be set when using "
            "--llm-backend prime_intellect_live. Set it in .env or export the variable."
        )
    return key


# Backend IDs that require OpenAI API key (for resolve_credentials and fail-fast).
OPENAI_KEY_BACKENDS = frozenset({"openai_live", "openai_responses", "openai_hosted"})

# Backend IDs that require Anthropic API key.
ANTHROPIC_KEY_BACKENDS = frozenset({"anthropic_live"})

# Prime Intellect Inference (pinference.ai).
PRIME_INTELLECT_KEY_BACKENDS = frozenset({"prime_intellect_live"})


def resolve_credentials(
    llm_backend: str,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """
    Resolve credentials for the given LLM backend.

    Ensures .env is loaded from repo_root (when set), then requires the
    appropriate API key for backends that need one. Returns a dict suitable
    for passing into backend constructors (e.g. OpenAILiveBackend(**creds, ...)).

    - openai_live / openai_responses / openai_hosted: returns {"api_key": key}
    - anthropic_live: returns {"api_key": key}
    - prime_intellect_live: returns {"api_key": key} (Prime Inference token)
    - ollama_live: returns {} (no secret)
    - deterministic / deterministic_constrained / etc.: returns {}

    Raises ValueError if a live backend requiring a key is selected and the key is missing.
    """
    _ensure_dotenv_loaded(repo_root)

    if llm_backend in OPENAI_KEY_BACKENDS:
        return {"api_key": _require_openai_api_key()}
    if llm_backend in ANTHROPIC_KEY_BACKENDS:
        return {"api_key": _require_anthropic_api_key()}
    if llm_backend in PRIME_INTELLECT_KEY_BACKENDS:
        return {"api_key": _require_prime_intellect_api_key()}
    # ollama_live and any other backends that do not need a secret
    return {}


def require_credentials_for_backend(llm_backend: str, repo_root: Path | None = None) -> None:
    """
    Fail-fast: ensure credentials are available for the given backend.
    Loads .env from repo_root, then raises ValueError if the backend needs
    an API key and it is not set. Call at runner entry before building envs.
    """
    if (
        llm_backend in OPENAI_KEY_BACKENDS
        or llm_backend in ANTHROPIC_KEY_BACKENDS
        or llm_backend in PRIME_INTELLECT_KEY_BACKENDS
    ):
        resolve_credentials(llm_backend, repo_root)
