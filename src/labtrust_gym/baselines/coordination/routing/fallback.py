"""
Deadlock-safe fallback: wait-in-place and priority aging.
Token-based corridor reservation can be added later; for now wait + aging.
"""

from __future__ import annotations


def safe_wait_policy() -> str:
    """
    Action type for "wait in place" (no move). Safe fallback when no path found.
    """
    return "NOOP"


def priority_aging(
    agent_id: str,
    wait_steps_by_agent: dict[str, int],
    max_boost: int = 100,
) -> int:
    """
    Priority boost for agents that have been waiting: older waiters get higher
    effective priority so they are planned first and break deadlocks.
    Returns non-negative boost to add to base priority (deterministic).
    """
    wait = wait_steps_by_agent.get(agent_id, 0)
    return min(max_boost, max(0, wait))
