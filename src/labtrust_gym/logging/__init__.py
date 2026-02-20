"""
Structured logging for runs: episode-level JSONL and step timing.

EpisodeLogger and helpers write one JSONL line per engine step (event + result)
so that runs can be replayed or analyzed. Deterministic: same seed and actions
yield the same log. step_timing (optional) records step and invariant durations
when LABTRUST_STEP_TIMING=1.
"""

from __future__ import annotations

from labtrust_gym.logging.episode_log import (
    EpisodeLogger,
    build_llm_coord_audit_digest_entry,
    build_llm_coord_proposal_attempt_entry,
    build_llm_coord_proposal_entry,
    build_log_entry,
    write_log_line,
)

__all__ = [
    "EpisodeLogger",
    "build_log_entry",
    "build_llm_coord_audit_digest_entry",
    "build_llm_coord_proposal_attempt_entry",
    "build_llm_coord_proposal_entry",
    "write_log_line",
]
