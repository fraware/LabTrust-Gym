"""
Optional deterministic policy-like backend for llm_offline.

Chooses from allowed_actions using a fixed preference order (e.g. prefer
START_RUN, then QUEUE_RUN, then MOVE, then TICK, then NOOP). Seeded RNG
breaks ties. No network; same interface as DeterministicConstrainedBackend.
Not used in CI; register as deterministic_policy_v1 when needed.
"""

from __future__ import annotations

import json
import random
# Preference order: first match in allowed_actions wins; ties broken by RNG
_DEFAULT_PREFERENCE_ORDER = (
    "START_RUN",
    "QUEUE_RUN",
    "RELEASE_RESULT",
    "MOVE",
    "OPEN_DOOR",
    "TICK",
    "NOOP",
)


def _allowed_actions_from_user_message(user_content: str) -> list[str]:
    """Extract allowed_actions from user message (same logic as agent)."""
    if user_content.strip().startswith("{"):
        try:
            payload = json.loads(user_content)
            if isinstance(payload, dict):
                allowed = payload.get("allowed_actions")
                if isinstance(allowed, list):
                    return [str(a) for a in allowed]
        except (json.JSONDecodeError, TypeError):
            pass
    prefix = "ALLOWED_ACTIONS_JSON:"
    if prefix in user_content:
        idx = user_content.find(prefix)
        rest = user_content[idx + len(prefix):].lstrip()
        line = rest.split("\n")[0].strip()
        if line.startswith("["):
            try:
                parsed = json.loads(line)
                if not isinstance(parsed, list) or not parsed:
                    return []
                first = parsed[0]
                if isinstance(first, str):
                    return [str(a) for a in parsed]
                if isinstance(first, dict) and first.get("action_type"):
                    return [
                        str(e.get("action_type", ""))
                        for e in parsed
                        if isinstance(e, dict) and e.get("action_type")
                    ]
            except (json.JSONDecodeError, TypeError):
                pass
    return []


class DeterministicPolicyBackend:
    """
    Picks from allowed_actions by preference order; seeded RNG for ties.
    No network; for llm_offline only. Same interface as
    DeterministicConstrainedBackend (generate(messages) -> str).
    """

    backend_id = "deterministic_policy_v1"
    model_id = "n/a"

    def __init__(
        self,
        seed: int,
        default_action_type: str = "NOOP",
        *,
        preference_order: tuple[str, ...] | None = None,
    ) -> None:
        self._seed = seed
        self._default_action_type = default_action_type
        self._preference_order = (
            preference_order or _DEFAULT_PREFERENCE_ORDER
        )
        self._call_count = 0

    def reset(self, seed: int) -> None:
        self._seed = seed
        self._call_count = 0

    def generate(self, messages: list[dict[str, str]]) -> str:
        user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        allowed_actions = _allowed_actions_from_user_message(user)
        if not allowed_actions:
            action_type = self._default_action_type
        else:
            ordered = [
                a for a in self._preference_order if a in allowed_actions
            ]
            if not ordered:
                action_type = allowed_actions[0]
            elif len(ordered) == 1:
                action_type = ordered[0]
            else:
                rng = random.Random(
                    self._seed + self._call_count * 7919
                )
                action_type = rng.choice(ordered)
        self._call_count += 1
        return json.dumps(
            {
                "action_type": action_type,
                "args": {},
                "reason_code": None,
                "token_refs": [],
                "rationale": "deterministic_policy_v1",
                "confidence": 0.9,
                "safety_notes": "",
            },
            sort_keys=True,
        )
