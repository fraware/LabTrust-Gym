"""
Deterministic adversary (sloppy) agent baseline for adversarial benchmarks.

Used to test containment and detection: misroutes work to the wrong device,
attempts unauthorized restricted-door access without a token, attempts
expired-token replay, and leaves doors open. Step-based and deterministic.
"""

from __future__ import annotations

from typing import Any

# Action indices aligned with pz_parallel
ACTION_NOOP = 0
ACTION_TICK = 1
ACTION_QUEUE_RUN = 2
ACTION_MOVE = 3
ACTION_OPEN_DOOR = 4
ACTION_START_RUN = 5

DEFAULT_DEVICE_IDS: list[str] = [
    "DEV_CENTRIFUGE_BANK_01",
    "DEV_ALIQUOTER_01",
    "DEV_CHEM_A_01",
    "DEV_CHEM_B_01",
    "DEV_HAEM_01",
    "DEV_COAG_01",
]
RESTRICTED_DOOR_ID = "D_RESTRICTED_AIRLOCK"


def _scalar(x: Any, default: int = 0) -> int:
    """Extract int from obs value."""
    if x is None:
        return default
    if hasattr(x, "item"):
        return int(x.item())
    if hasattr(x, "__len__") and len(x) > 0:
        return int(x.flat[0]) if hasattr(x, "flat") else int(x[0])
    return int(x)


class AdversaryAgent:
    """
    Deterministic adversary: misroute, unauthorized door, expired token, leave door open.

    Schedule (by _step_counter, 0-based):
    - 0-1: NOOP
    - 2: QUEUE_RUN to wrong device (work_id from obs or default; device_id = DEV_COAG_01 for chem work)
    - 3-4: NOOP
    - 5: OPEN_DOOR restricted without token (attempt unauthorized)
    - 6-7: NOOP
    - 8: OPEN_DOOR with token_refs ["T_EXPIRED"] (attempt replay/expired)
    - 9-10: NOOP
    - 11: OPEN_DOOR (leave door open)
    - 12+: NOOP (no TICK to mitigate; door stays open until another agent TICKs)
    """

    def __init__(
        self,
        device_ids: list[str] | None = None,
        misroute_step: int = 2,
        unauthorized_door_step: int = 5,
        expired_token_step: int = 8,
        leave_door_open_step: int = 11,
    ) -> None:
        self._device_ids = device_ids or list(DEFAULT_DEVICE_IDS)
        self._misroute_step = misroute_step
        self._unauthorized_door_step = unauthorized_door_step
        self._expired_token_step = expired_token_step
        self._leave_door_open_step = leave_door_open_step
        self._step_counter = 0

    def act(
        self,
        observation: dict[str, Any],
        agent_id: str = "adversary_0",
    ) -> tuple[int, dict[str, Any]]:
        """
        Return (action_index, action_info). Deterministic by step counter.
        """
        step = self._step_counter
        self._step_counter += 1
        action_info: dict[str, Any] = {}

        log_frozen = _scalar(observation.get("log_frozen"), 0)
        if log_frozen:
            return (ACTION_NOOP, action_info)

        # Misroute: QUEUE_RUN to wrong device (e.g. chem analyzer work to coag)
        if step == self._misroute_step:
            wrong_device = "DEV_COAG_01"
            if wrong_device not in self._device_ids:
                wrong_device = self._device_ids[-1] if self._device_ids else ""
            action_info = {
                "device_id": wrong_device,
                "work_id": f"adv_misroute_{step}",
                "priority": "ROUTINE",
            }
            return (ACTION_QUEUE_RUN, action_info)

        # Attempt unauthorized restricted door (no token_refs)
        if step == self._unauthorized_door_step:
            action_info = {"door_id": RESTRICTED_DOOR_ID}
            return (ACTION_OPEN_DOOR, action_info)

        # Attempt expired token / replay (token_refs rejected by engine)
        if step == self._expired_token_step:
            action_info = {
                "door_id": RESTRICTED_DOOR_ID,
                "token_refs": ["T_EXPIRED"],
            }
            return (ACTION_OPEN_DOOR, action_info)

        # Leave door open (OPEN_DOOR then never TICK)
        if step == self._leave_door_open_step:
            action_info = {"door_id": RESTRICTED_DOOR_ID}
            return (ACTION_OPEN_DOOR, action_info)

        return (ACTION_NOOP, action_info)
