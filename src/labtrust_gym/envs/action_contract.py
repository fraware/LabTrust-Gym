"""
Single source of truth for per-step action indices used by the PZ env,
coordination interface, baselines, and risk injectors.

Action dict has action_index in 0..5 and optionally action_type, args,
reason_code, token_refs.
"""

from __future__ import annotations

NUM_ACTION_TYPES = 6
ACTION_NOOP = 0
ACTION_TICK = 1
ACTION_QUEUE_RUN = 2
ACTION_MOVE = 3
ACTION_OPEN_DOOR = 4
ACTION_START_RUN = 5
VALID_ACTION_INDICES = frozenset({0, 1, 2, 3, 4, 5})

ACTION_INDEX_TO_TYPE: dict[int, str] = {
    0: "NOOP",
    1: "TICK",
    2: "QUEUE_RUN",
    3: "MOVE",
    4: "OPEN_DOOR",
    5: "START_RUN",
}

__all__ = [
    "NUM_ACTION_TYPES",
    "ACTION_NOOP",
    "ACTION_TICK",
    "ACTION_QUEUE_RUN",
    "ACTION_MOVE",
    "ACTION_OPEN_DOOR",
    "ACTION_START_RUN",
    "VALID_ACTION_INDICES",
    "ACTION_INDEX_TO_TYPE",
]
