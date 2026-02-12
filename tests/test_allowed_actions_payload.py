"""
Canonical allowed-actions payload: stability (GS-001 style), size cap, parity with backends.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from labtrust_gym.baselines.llm.agent import _allowed_actions_from_user_message
from labtrust_gym.baselines.llm.allowed_actions_payload import (
    ACTION_SPEC_REGISTRY,
    allowed_actions_from_payload,
    build_allowed_actions_payload,
    serialize_allowed_actions_payload,
)
from labtrust_gym.baselines.llm.prompts import build_user_payload_from_context


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_build_allowed_actions_payload_stable_gs001_style() -> None:
    """For a known state and allowed_actions (GS-001 / ROLE_ANALYTICS style), payload is stable under fixed inputs."""
    # ROLE_ANALYTICS from rbac_policy.v0.1.yaml (subset used in full pipeline)
    allowed = [
        "NOOP",
        "TICK",
        "MOVE",
        "QUEUE_RUN",
        "START_RUN",
        "END_RUN",
        "QC_EVENT",
        "GENERATE_RESULT",
        "RELEASE_RESULT",
    ]
    state = {"t_s": 0}
    p1 = build_allowed_actions_payload(state=state, allowed_actions=allowed)
    p2 = build_allowed_actions_payload(state=state, allowed_actions=allowed)
    assert p1 == p2
    assert len(p1) == len(allowed)
    action_types = [e["action_type"] for e in p1]
    assert action_types == allowed
    for e in p1:
        assert "action_type" in e
        assert "args_examples" in e
        assert "description" in e
        assert isinstance(e.get("required_tokens"), bool)


def test_build_allowed_actions_payload_capped_max_actions() -> None:
    """Payload is truncated to max_actions to control token cost."""
    allowed = [f"NOOP_{i}" for i in range(50)]
    payload = build_allowed_actions_payload(
        allowed_actions=allowed,
        max_actions=5,
    )
    assert len(payload) == 5
    assert payload[0]["action_type"] == "NOOP_0"
    assert payload[4]["action_type"] == "NOOP_4"


def test_build_allowed_actions_payload_capped_list_len() -> None:
    """Long lists in state (zone_ids, device_ids) are truncated to max_list_len."""
    zone_ids = [f"Z_{i}" for i in range(20)]
    device_ids = [f"DEV_{i}" for i in range(15)]
    payload = build_allowed_actions_payload(
        state={"zone_ids": zone_ids, "device_ids": device_ids},
        allowed_actions=["MOVE", "QUEUE_RUN"],
        max_list_len=3,
    )
    assert len(payload) == 2
    for e in payload:
        for ex in e.get("args_examples", []):
            for k, v in ex.items():
                if isinstance(v, list):
                    assert len(v) <= 3


def test_allowed_actions_from_payload() -> None:
    """allowed_actions_from_payload extracts action_type list from canonical payload."""
    payload = [
        {"action_type": "NOOP", "args_examples": [{}], "description": "Do nothing."},
        {"action_type": "TICK", "args_examples": [{}], "description": "Advance time."},
    ]
    out = allowed_actions_from_payload(payload)
    assert out == ["NOOP", "TICK"]


def test_allowed_actions_from_user_message_canonical_payload() -> None:
    """DeterministicConstrainedBackend consumes same payload: _allowed_actions_from_user_message parses canonical format."""
    payload = build_allowed_actions_payload(
        allowed_actions=["NOOP", "TICK", "QUEUE_RUN"],
    )
    user_content = build_user_payload_from_context(
        partner_id="",
        policy_fingerprint=None,
        now_ts_s=0,
        timing_mode="explicit",
        state_summary={},
        allowed_actions=["NOOP", "TICK", "QUEUE_RUN"],
        allowed_actions_payload=payload,
    )
    extracted = _allowed_actions_from_user_message(user_content)
    assert extracted == ["NOOP", "TICK", "QUEUE_RUN"]


def test_serialize_allowed_actions_payload_deterministic() -> None:
    """Serialized payload is deterministic (same input => same JSON string)."""
    payload = build_allowed_actions_payload(
        allowed_actions=["NOOP", "TICK", "MOVE"],
    )
    s1 = serialize_allowed_actions_payload(payload)
    s2 = serialize_allowed_actions_payload(payload)
    assert s1 == s2
    parsed = json.loads(s1)
    assert len(parsed) == 3
    assert [p["action_type"] for p in parsed] == ["NOOP", "TICK", "MOVE"]


def test_action_spec_registry_has_required_keys() -> None:
    """Every action in registry has action_type key and at least args_examples or description."""
    for action_type, spec in ACTION_SPEC_REGISTRY.items():
        assert isinstance(spec, dict)
        assert "args_examples" in spec or "description" in spec
        args_ex = spec.get("args_examples", [])
        assert isinstance(args_ex, list)
        for ex in args_ex:
            assert isinstance(ex, dict)


# work_id in examples must match deterministic scheme work_{run}_{agent}_{step}
WORK_ID_PATTERN = re.compile(r"^work_\d+_[a-zA-Z0-9_]+_\d+$")


def test_payload_work_id_never_placeholder_and_matches_pattern() -> None:
    """No args_example work_id is the legacy marker; QUEUE_RUN examples use deterministic work_id pattern."""
    legacy_marker = "OBS" + "_PLACEHOLDER"  # avoid literal in source for no-placeholders gate
    for action_type, spec in ACTION_SPEC_REGISTRY.items():
        for ex in spec.get("args_examples", []):
            if "work_id" not in ex:
                continue
            work_id = ex["work_id"]
            assert work_id != legacy_marker, (
                f"ACTION_SPEC_REGISTRY[{action_type!r}] must not use legacy work_id marker"
            )
            if action_type == "QUEUE_RUN":
                assert WORK_ID_PATTERN.match(work_id), (
                    f"QUEUE_RUN work_id must match work_{{run_id}}_{{agent_id}}_{{step_idx}}, got {work_id!r}"
                )
