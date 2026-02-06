"""
Deterministic insider adversary for TaskF: RBAC bypass, forged signature, replay, revoked key, token misuse.

Attack phases (by step, 0-based):
(1) Forbidden action: RELEASE_RESULT -> RBAC_ACTION_DENY
(2) Forged signature: MOVE with key_id + invalid signature -> SIG_INVALID
(3) Replay: same invalid signature again (different event_id/prev_hash) -> SIG_INVALID
(4) Revoked key: MOVE with revoked key_id -> SIG_KEY_REVOKED
(5) Token misuse: RELEASE_RESULT_OVERRIDE with fake token -> RBAC_ACTION_DENY (token cannot bypass RBAC)
"""

from __future__ import annotations

import base64
from typing import Any

# Use NOOP index; action_info carries action_type override for env
ACTION_NOOP = 0

# Step indices for each attack phase (deterministic)
PHASE1_RELEASE_STEP = 2
PHASE2_FORGED_SIG_STEP = 5
PHASE3_REPLAY_STEP = 8
PHASE4_REVOKED_KEY_STEP = 11
PHASE5_TOKEN_MISUSE_STEP = 14

# Forged signature (64 bytes base64) - wrong for any real payload
FORGED_SIGNATURE_B64 = base64.b64encode(b"x" * 64).decode()


class InsiderAdversaryAgent:
    """
    Deterministic insider: limited RBAC role; attempts forbidden action, forged sig, replay, token misuse.
    Returns (ACTION_NOOP, action_info) with action_info containing action_type and args (and key_id/signature/token_refs when needed).
    """

    def __init__(
        self,
        phase1_step: int = PHASE1_RELEASE_STEP,
        phase2_step: int = PHASE2_FORGED_SIG_STEP,
        phase3_step: int = PHASE3_REPLAY_STEP,
        phase4_step: int = PHASE4_REVOKED_KEY_STEP,
        phase5_step: int = PHASE5_TOKEN_MISUSE_STEP,
    ) -> None:
        self._phase1_step = phase1_step
        self._phase2_step = phase2_step
        self._phase3_step = phase3_step
        self._phase4_step = phase4_step
        self._phase5_step = phase5_step
        self._step_counter = 0

    def act(
        self,
        observation: dict[str, Any],
        agent_id: str = "adversary_insider_0",
    ) -> tuple[int, dict[str, Any]]:
        """
        Return (action_index, action_info). action_info may contain action_type, args, key_id, signature, token_refs for custom event.
        """
        step = self._step_counter
        self._step_counter += 1
        action_info: dict[str, Any] = {}

        # Phase 1: forbidden action (RELEASE_RESULT without role)
        if step == self._phase1_step:
            action_info = {
                "action_type": "RELEASE_RESULT",
                "args": {"result_id": "R_INSIDER_ANY"},
                "reason_code": None,
                "token_refs": [],
            }
            return (ACTION_NOOP, action_info)

        # Phase 2: forged signature (MOVE with invalid signature)
        if step == self._phase2_step:
            action_info = {
                "action_type": "MOVE",
                "args": {
                    "entity_type": "Agent",
                    "entity_id": "A_INSIDER_0",
                    "from_zone": "Z_SORTING_LANES",
                    "to_zone": "Z_ACCESSIONING",
                },
                "reason_code": None,
                "token_refs": [],
                "key_id": "ed25519:key_reception",
                "signature": FORGED_SIGNATURE_B64,
            }
            return (ACTION_NOOP, action_info)

        # Phase 3: replay (same forged signature; different event_id/prev_hash => verify fails)
        if step == self._phase3_step:
            action_info = {
                "action_type": "MOVE",
                "args": {
                    "entity_type": "Agent",
                    "entity_id": "A_INSIDER_0",
                    "from_zone": "Z_SORTING_LANES",
                    "to_zone": "Z_PREANALYTICS",
                },
                "reason_code": None,
                "token_refs": [],
                "key_id": "ed25519:key_reception",
                "signature": FORGED_SIGNATURE_B64,
            }
            return (ACTION_NOOP, action_info)

        # Phase 4: revoked key (MOVE with revoked key_id -> SIG_KEY_REVOKED)
        if step == self._phase4_step:
            action_info = {
                "action_type": "MOVE",
                "args": {
                    "entity_type": "Agent",
                    "entity_id": "A_INSIDER_0",
                    "from_zone": "Z_SORTING_LANES",
                    "to_zone": "Z_ACCESSIONING",
                },
                "reason_code": None,
                "token_refs": [],
                "key_id": "ed25519:key_revoked",
                "signature": FORGED_SIGNATURE_B64,
            }
            return (ACTION_NOOP, action_info)

        # Phase 5: token misuse (RELEASE_RESULT_OVERRIDE with token; RBAC still denies)
        if step == self._phase5_step:
            action_info = {
                "action_type": "RELEASE_RESULT_OVERRIDE",
                "args": {"result_id": "R_INSIDER_ANY", "reason_code": "TIME_EXPIRED"},
                "reason_code": "TIME_EXPIRED",
                "token_refs": ["T_OVR_INSIDER_FAKE"],
            }
            return (ACTION_NOOP, action_info)

        return (ACTION_NOOP, {})
