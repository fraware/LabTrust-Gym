"""
Pipeline mode configuration: deterministic vs LLM offline vs LLM live.

- deterministic: scripted agents only; no LLM interface; no network.
- llm_offline: LLM agent interface with deterministic backend only; no network.
- llm_live: allows network-backed LLM backends; requires explicit --allow-network
  or LABTRUST_ALLOW_NETWORK=1.

Network is forbidden in deterministic and llm_offline; call check_network_allowed()
before any HTTP.
"""

from __future__ import annotations

import sys
from typing import Any, Literal

PipelineMode = Literal["deterministic", "llm_offline", "llm_live"]

_DEFAULT_MODE: PipelineMode = "deterministic"
_state: dict[str, Any] = {
    "pipeline_mode": _DEFAULT_MODE,
    "allow_network": False,
    "llm_backend_id": None,
}


def get_pipeline_mode() -> PipelineMode:
    """Return current pipeline mode."""
    return _state["pipeline_mode"]


def is_network_allowed() -> bool:
    """Return True if network is allowed (llm_live + explicit opt-in)."""
    return bool(_state["allow_network"])


def get_llm_backend_id() -> str | None:
    """Return current LLM backend id for banner."""
    return _state.get("llm_backend_id")


def set_pipeline_config(
    pipeline_mode: PipelineMode,
    allow_network: bool = False,
    llm_backend_id: str | None = None,
) -> None:
    """
    Set pipeline configuration. Call at CLI/runner entry before any benchmark
    or LLM use.

    - For deterministic and llm_offline, allow_network must be False
      (enforced at use site).
    - For llm_live, allow_network must be True to use live backends
      (enforced at CLI).
    """
    _state["pipeline_mode"] = pipeline_mode
    _state["allow_network"] = allow_network
    _state["llm_backend_id"] = llm_backend_id


def check_network_allowed() -> None:
    """
    Raise RuntimeError if network is not allowed (deterministic or llm_offline).
    Call this before any HTTP/API call in LLM backends.
    """
    if _state["allow_network"]:
        return
    mode = _state["pipeline_mode"]
    raise RuntimeError(
        "Network is not allowed in this pipeline mode. "
        f"Current mode: {mode!r}. "
        "To use live LLM backends (openai_live, ollama_live), set pipeline_mode "
        "to 'llm_live' and pass --allow-network or set LABTRUST_ALLOW_NETWORK=1."
    )


def require_llm_live_allow_network() -> None:
    """
    Raise RuntimeError if pipeline_mode is llm_live but allow_network is False.
    Call when user requests openai_live or ollama_live to enforce explicit
    opt-in.
    """
    if _state["pipeline_mode"] != "llm_live":
        return
    if _state["allow_network"]:
        return
    raise RuntimeError(
        "Live LLM backends (openai_live, ollama_live) require explicit network "
        "permission. Pass --allow-network or set LABTRUST_ALLOW_NETWORK=1."
    )


def print_startup_banner() -> None:
    """Print pipeline_mode, llm_backend id (if any), and whether network allowed."""
    mode = _state["pipeline_mode"]
    backend = _state.get("llm_backend_id") or "none"
    net = "allowed" if _state["allow_network"] else "disabled"
    line = f"[LabTrust] pipeline_mode={mode!r} llm_backend={backend!r} network={net}"
    print(line, file=sys.stderr)
    if mode == "llm_live" and _state["allow_network"]:
        _print_llm_live_warning()


def _print_llm_live_warning() -> None:
    """Print red warning that this run will make network calls and may incur cost."""
    red = "\033[31m"
    reset = "\033[0m"
    msg = "WILL MAKE NETWORK CALLS / MAY INCUR COST"
    print(f"{red}[LabTrust] {msg}{reset}", file=sys.stderr)
