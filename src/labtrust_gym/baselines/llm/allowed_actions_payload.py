"""
Canonical allowed-actions JSON payload for LLM user prompt.

- build_allowed_actions_payload(state, allowed_actions, ...) -> list of dicts.
- Each entry: action_type, args_examples (or args_schema), required_tokens (optional), description.
- Deterministic and size-capped for token cost control.
- Used verbatim by DeterministicConstrainedBackend and OpenAILiveBackend.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# Default zone/device lists (aligned with pz_parallel; avoid circular import)
DEFAULT_ZONE_IDS: List[str] = [
    "Z_SRA_RECEPTION",
    "Z_ACCESSIONING",
    "Z_SORTING_LANES",
    "Z_PREANALYTICS",
    "Z_CENTRIFUGE_BAY",
    "Z_ALIQUOT_LABEL",
    "Z_ANALYZER_HALL_A",
    "Z_ANALYZER_HALL_B",
    "Z_QC_SUPERVISOR",
    "Z_RESTRICTED_BIOHAZARD",
]
DEFAULT_DEVICE_IDS: List[str] = [
    "DEV_CENTRIFUGE_BANK_01",
    "DEV_ALIQUOTER_01",
    "DEV_CHEM_A_01",
    "DEV_CHEM_B_01",
    "DEV_HAEM_01",
    "DEV_COAG_01",
]
RESTRICTED_DOOR_ID = "D_RESTRICTED_AIRLOCK"

# Cap for token cost control
DEFAULT_MAX_ACTIONS = 32
DEFAULT_MAX_LIST_LEN = 8

# Action spec: args_examples, required_tokens (optional), description
ACTION_SPEC_REGISTRY: Dict[str, Dict[str, Any]] = {
    "NOOP": {
        "args_examples": [{}],
        "required_tokens": False,
        "description": "Do nothing this step.",
    },
    "TICK": {
        "args_examples": [{}],
        "required_tokens": False,
        "description": "Advance time only.",
    },
    "QUEUE_RUN": {
        "args_examples": [
            {
                "device_id": "DEV_CHEM_A_01",
                "work_id": "OBS_PLACEHOLDER",
                "priority_class": "ROUTINE",
            },
            {
                "device_id": "DEV_HAEM_01",
                "work_id": "OBS_PLACEHOLDER",
                "priority_class": "STAT",
            },
        ],
        "required_tokens": False,
        "description": "Queue run (device_id, work_id, priority_class: ROUTINE|STAT|URGENT).",
    },
    "MOVE": {
        "args_examples": [
            {"from_zone": "Z_SRA_RECEPTION", "to_zone": "Z_ACCESSIONING"},
            {"from_zone": "Z_SORTING_LANES", "to_zone": "Z_PREANALYTICS"},
        ],
        "required_tokens": False,
        "description": "Move agent between zones (from_zone, to_zone).",
    },
    "OPEN_DOOR": {
        "args_examples": [
            {"door_id": RESTRICTED_DOOR_ID, "token_refs": ["TOKEN_RESTRICTED_*"]},
        ],
        "required_tokens": True,
        "description": "Open restricted door; token_refs required for restricted doors.",
    },
    "START_RUN": {
        "args_examples": [
            {"device_id": "DEV_CHEM_A_01", "work_id": "work_001"},
            {"device_id": "DEV_HAEM_01", "work_id": "work_002"},
        ],
        "required_tokens": False,
        "description": "Start a run on device (device_id, work_id).",
    },
    "RELEASE_RESULT": {
        "args_examples": [{"result_id": "R1"}],
        "required_tokens": False,
        "description": "Release result to ordering (result_id).",
    },
    "RELEASE_RESULT_OVERRIDE": {
        "args_examples": [{"result_id": "R1"}, {"result_id": "R2"}],
        "required_tokens": True,
        "description": "Override release; may require override token.",
    },
    "HOLD_RESULT": {
        "args_examples": [{"result_id": "R1"}],
        "required_tokens": False,
        "description": "Hold result (result_id).",
    },
    "CREATE_ACCESSION": {
        "args_examples": [{"specimen_id": "S1"}],
        "required_tokens": False,
        "description": "Create accession for specimen (specimen_id).",
    },
    "ACCEPT_SPECIMEN": {
        "args_examples": [{"specimen_id": "S1"}],
        "required_tokens": False,
        "description": "Accept specimen (specimen_id).",
    },
    "REJECT_SPECIMEN": {
        "args_examples": [{"specimen_id": "S1"}],
        "required_tokens": False,
        "description": "Reject specimen (specimen_id).",
    },
    "HOLD_SPECIMEN": {
        "args_examples": [{"specimen_id": "S1"}],
        "required_tokens": False,
        "description": "Hold specimen (specimen_id).",
    },
    "CHECK_ACCEPTANCE_RULES": {
        "args_examples": [{}],
        "required_tokens": False,
        "description": "Check acceptance rules.",
    },
    "CENTRIFUGE_START": {
        "args_examples": [{"device_id": "DEV_CENTRIFUGE_BANK_01"}],
        "required_tokens": False,
        "description": "Start centrifuge (device_id).",
    },
    "CENTRIFUGE_END": {
        "args_examples": [{"device_id": "DEV_CENTRIFUGE_BANK_01"}],
        "required_tokens": False,
        "description": "End centrifuge (device_id).",
    },
    "ALIQUOT_CREATE": {
        "args_examples": [{"device_id": "DEV_ALIQUOTER_01"}],
        "required_tokens": False,
        "description": "Create aliquot (device_id).",
    },
    "END_RUN": {
        "args_examples": [{"device_id": "DEV_CHEM_A_01", "work_id": "work_001"}],
        "required_tokens": False,
        "description": "End run (device_id, work_id).",
    },
    "QC_EVENT": {
        "args_examples": [{"device_id": "DEV_CHEM_A_01"}, {"result_id": "R1"}],
        "required_tokens": False,
        "description": "QC event (device_id or result_id).",
    },
    "GENERATE_RESULT": {
        "args_examples": [{"device_id": "DEV_CHEM_A_01", "work_id": "work_001"}],
        "required_tokens": False,
        "description": "Generate result (device_id, work_id).",
    },
    "MINT_TOKEN": {
        "args_examples": [{"token_type": "RESTRICTED"}, {"token_type": "OVERRIDE"}],
        "required_tokens": False,
        "description": "Mint token (token_type). Supervisor/security only.",
    },
    "REVOKE_TOKEN": {
        "args_examples": [{"token_id": "TOKEN_*"}],
        "required_tokens": False,
        "description": "Revoke token (token_id).",
    },
    "CONSUME_TOKEN": {
        "args_examples": [{"token_refs": ["TOKEN_RESTRICTED_*"]}],
        "required_tokens": False,
        "description": "Consume token (token_refs).",
    },
}


def _truncate_list(lst: List[Any], max_len: int) -> List[Any]:
    """Return list truncated to max_len (deterministic)."""
    if max_len <= 0 or not lst:
        return list(lst)
    return list(lst[:max_len])


def build_allowed_actions_payload(
    state: Optional[Dict[str, Any]] = None,
    allowed_actions: Optional[List[str]] = None,
    zone_ids: Optional[List[str]] = None,
    device_ids: Optional[List[str]] = None,
    max_actions: int = DEFAULT_MAX_ACTIONS,
    max_list_len: int = DEFAULT_MAX_LIST_LEN,
) -> List[Dict[str, Any]]:
    """
    Build canonical allowed-actions JSON payload for the user prompt.

    Each entry: action_type, args_examples, required_tokens (optional), description.
    Deterministic: same state + allowed_actions => same payload (order preserved, capped).
    Payload size capped (max_actions, truncate long lists) to control token costs.

    Args:
        state: Optional observation/state summary (zone_ids, device_ids keyed).
        allowed_actions: List of action_type strings from RBAC.
        zone_ids: Optional zone list for MOVE args_examples; truncated to max_list_len.
        device_ids: Optional device list for QUEUE_RUN/START_RUN; truncated.
        max_actions: Maximum number of actions in payload (default 32).
        max_list_len: Maximum length of any list in args_examples (default 8).

    Returns:
        List of dicts: action_type, args_examples, required_tokens, description.
    """
    state = state or {}
    allowed_actions = allowed_actions or []
    payload: List[Dict[str, Any]] = []
    for action_type in allowed_actions:
        if len(payload) >= max_actions:
            break
        action_type = str(action_type).strip()
        if not action_type:
            continue
        spec = ACTION_SPEC_REGISTRY.get(action_type)
        if spec is None:
            payload.append(
                {
                    "action_type": action_type,
                    "args_examples": [{}],
                    "required_tokens": False,
                    "description": f"Action: {action_type}.",
                }
            )
            continue
        args_examples = spec.get("args_examples") or [{}]
        if isinstance(args_examples, list) and args_examples:
            examples = []
            for ex in args_examples[:max_list_len]:
                if not isinstance(ex, dict):
                    continue
                ex = dict(ex)
                for k, v in list(ex.items()):
                    if isinstance(v, list) and len(v) > max_list_len:
                        ex[k] = v[:max_list_len]
                examples.append(ex)
            if not examples:
                examples = [{}]
        else:
            examples = [{}]
        required_tokens = spec.get("required_tokens", False)
        description = spec.get("description", f"Action: {action_type}.")
        entry: Dict[str, Any] = {
            "action_type": action_type,
            "args_examples": examples,
            "description": description,
        }
        if required_tokens is not None:
            entry["required_tokens"] = bool(required_tokens)
        payload.append(entry)
    return payload


def allowed_actions_from_payload(payload: List[Dict[str, Any]]) -> List[str]:
    """Extract list of action_type strings from canonical payload (for decoder/shield parity)."""
    out: List[str] = []
    for e in payload:
        if isinstance(e, dict) and e.get("action_type"):
            out.append(str(e["action_type"]))
    return out


def serialize_allowed_actions_payload(payload: List[Dict[str, Any]]) -> str:
    """Canonical JSON string for payload (deterministic sort_keys)."""
    return json.dumps(payload, sort_keys=True)
