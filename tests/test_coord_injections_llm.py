"""
LLM-relevant coordination injections: deterministic triggers, expected reason codes
and metrics. When shield is strict, success must not occur (detection/containment).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from labtrust_gym.security.risk_injections import make_injector

# Injection IDs added for LLM/coord coverage (policy/coordination/injections.v0.2.yaml)
LLM_COORD_INJECTION_IDS = [
    "INJ-LLM-PROMPT-INJECT-COORD-001",
    "INJ-LLM-TOOL-ESCALATION-001",
    "INJ-COMMS-FLOOD-LLM-001",
    "INJ-ID-REPLAY-COORD-001",
    "INJ-COLLUSION-MARKET-001",
    "INJ-MEMORY-POISON-COORD-001",
]
# Coord protocol-targeted injections (INJ-COORD-*)
COORD_PROTOCOL_INJECTION_IDS = [
    "INJ-COORD-PROMPT-INJECT-001",
    "INJ-COORD-PLAN-REPLAY-001",
    "INJ-COORD-BID-SHILL-001",
]

# Reason codes that indicate detection/containment for these injectors
DETECTION_REASON_CODES = [
    "PROMPT_INJECTION_DETECTED",
    "UNTRUSTED_NOTE_AS_INSTRUCTION",
    "TOOL_NOT_IN_REGISTRY",
    "TOOL_NOT_ALLOWED_FOR_ROLE",
    "COORD_REPLAY_DETECTED",
    "SIG_INVALID",
    "LLM_INVALID_SCHEMA",
    "RC_DEVICE_UNKNOWN",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _injection_sequence_signature(
    seed: int,
    injection_id: str,
    steps: int,
    intensity: float = 1.0,
    seed_offset: int = 0,
) -> str:
    """Deterministic signature of mutation pattern over steps (obs + actions)."""
    inj = make_injector(
        injection_id, intensity=intensity, seed_offset=seed_offset
    )
    inj.reset(seed, None)
    obs = {
        "ops_0": {"queue_has_head": [0, 1], "zone_id": "Z_A"},
        "runner_0": {"zone_id": "Z_B"},
        "runner_1": {"zone_id": "Z_A"},
    }
    actions_dict = {
        "ops_0": {"action_index": 5, "action_type": "START_RUN", "args": {}},
        "runner_0": {"action_index": 5},
        "runner_1": {"action_index": 3},
    }
    recs = []
    for step in range(steps):
        obs, audit_obs = inj.mutate_obs(obs)
        act, audit_actions = inj.mutate_actions(actions_dict)
        rec = {
            "step": step,
            "audit_obs": audit_obs is not None,
            "audit_actions": len(audit_actions),
        }
        if audit_obs:
            rec["injection_id"] = audit_obs.get("injection_id")
        for aid in act:
            ad = act.get(aid) or {}
            if ad.get("_malicious_note") or ad.get("_poisoned_coord_fact"):
                rec["obs_mutation"] = (aid, list(ad.keys()))
                break
            if ad.get("action_type") == "INVOKE_TOOL":
                rec["tool_escalation"] = aid
                break
        recs.append(json.dumps(rec, sort_keys=True))
    return hashlib.sha256("\n".join(recs).encode()).hexdigest()


@pytest.mark.parametrize("injection_id", LLM_COORD_INJECTION_IDS)
def test_llm_coord_injection_deterministic_triggers(
    injection_id: str,
) -> None:
    """Same seed produces identical mutation sequence for each LLM coord injection."""
    seed = 12345
    steps = 20
    h1 = _injection_sequence_signature(seed, injection_id, steps)
    h2 = _injection_sequence_signature(seed, injection_id, steps)
    assert h1 == h2, (
        f"{injection_id}: same seed must yield same sequence hash"
    )


@pytest.mark.parametrize("injection_id", LLM_COORD_INJECTION_IDS)
def test_llm_coord_injection_make_and_reset(injection_id: str) -> None:
    """Each LLM coord injection_id is known and resets without error."""
    inj = make_injector(injection_id, intensity=0.5, seed_offset=1)
    assert inj.injection_id == injection_id
    inj.reset(99, None)
    assert inj._step == 0 or inj._rng is not None or hasattr(
        inj, "get_comms_config"
    )


def test_prompt_inject_coord_applies_at_deterministic_step() -> None:
    """INJ-LLM-PROMPT-INJECT-COORD-001 applies at a step determined by seed."""
    inj = make_injector(
        "INJ-LLM-PROMPT-INJECT-COORD-001", intensity=1.0, seed_offset=0
    )
    inj.reset(7, None)
    obs = {"ops_0": {"zone_id": "Z_A"}, "runner_0": {"zone_id": "Z_B"}}
    applied_step = None
    for step in range(25):
        obs, audit = inj.mutate_obs(obs)
        if audit is not None and "_malicious_note" in str(obs):
            applied_step = step
            break
        inj.observe_step([])
    assert applied_step is not None, "Injection must apply within 25 steps"
    inj2 = make_injector(
        "INJ-LLM-PROMPT-INJECT-COORD-001", intensity=1.0, seed_offset=0
    )
    inj2.reset(7, None)
    obs2 = {"ops_0": {"zone_id": "Z_A"}, "runner_0": {"zone_id": "Z_B"}}
    for step in range(25):
        obs2, audit = inj2.mutate_obs(obs2)
        if audit is not None:
            assert step == applied_step, "Same seed => same apply step"
            break
        inj2.observe_step([])


def test_tool_escalation_injection_produces_invalid_tool_action() -> None:
    """INJ-LLM-TOOL-ESCALATION-001 mutate_actions yields INVOKE_TOOL with invalid id."""
    inj = make_injector(
        "INJ-LLM-TOOL-ESCALATION-001", intensity=1.0, seed_offset=0
    )
    inj.reset(11, None)
    actions = {
        "ops_0": {"action_index": 5},
        "runner_0": {"action_index": 0},
    }
    found = False
    for _ in range(20):
        out, audits = inj.mutate_actions(actions)
        for aid, ad in out.items():
            if ad.get("action_type") == "INVOKE_TOOL":
                assert "FORBIDDEN_TOOL" in str(ad.get("args", {}))
                found = True
                break
        if found:
            break
        inj.observe_step([])
    assert found, "Tool escalation must apply within 20 steps"


def test_detection_reason_codes_prevent_attack_success() -> None:
    """When step_outputs contain BLOCKED with detection reason, attack_success stays False."""
    for injection_id in [
        "INJ-LLM-PROMPT-INJECT-COORD-001",
        "INJ-LLM-TOOL-ESCALATION-001",
        "INJ-ID-REPLAY-COORD-001",
    ]:
        inj = make_injector(injection_id, intensity=1.0, seed_offset=0)
        inj.reset(42, None)
        for reason in DETECTION_REASON_CODES[:4]:
            inj._applied_this_step = True
            step_outputs = [
                {
                    "status": "BLOCKED",
                    "blocked_reason_code": reason,
                    "emits": [],
                },
            ]
            inj.observe_step(step_outputs)
            assert inj._attack_success is False, (
                f"{injection_id}: BLOCKED with {reason} => no attack_success"
            )


def test_containment_sets_first_containment_step() -> None:
    """observe_step with BLOCKED sets first_containment_step and emits CONTAINED."""
    inj = make_injector("INJ-LLM-TOOL-ESCALATION-001", intensity=1.0)
    inj.reset(1, None)
    inj._applied_this_step = True
    step_outputs = [
        {"status": "BLOCKED", "blocked_reason_code": "TOOL_NOT_IN_REGISTRY"},
    ]
    extra = inj.observe_step(step_outputs)
    assert inj._first_containment_step is not None
    assert any(
        "SECURITY_INJECTION_CONTAINED" in (e.get("emits") or [])
        for e in extra
    )


def test_llm_injections_listed_in_injections_v02() -> None:
    """All LLM coord injection IDs exist in policy/coordination/injections.v0.2.yaml."""
    from labtrust_gym.policy.loader import load_yaml

    root = _repo_root()
    path = root / "policy" / "coordination" / "injections.v0.2.yaml"
    assert path.exists()
    data = load_yaml(path)
    injections = data.get("injections") or []
    ids = {i.get("injection_id") for i in injections if i.get("injection_id")}
    for iid in LLM_COORD_INJECTION_IDS + COORD_PROTOCOL_INJECTION_IDS:
        assert iid in ids, f"{iid} must be in injections.v0.2.yaml"
        entry = next((e for e in injections if e.get("injection_id") == iid))
        assert entry.get("success_definition")
        assert entry.get("detection_definition")
        assert entry.get("containment_definition")
