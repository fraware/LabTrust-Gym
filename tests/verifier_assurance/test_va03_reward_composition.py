"""LT-VA-03 reward composition and legacy parity tests."""

from __future__ import annotations

import copy

import pytest

from labtrust_gym.verifier_assurance.reward.composition import (
    COMPONENT_VOCAB,
    RewardComposer,
    RewardCompositionError,
    apply_legacy_rewards,
    build_reward_evidence_envelope,
    compose_components,
    legacy_compat_policy,
    validate_composition_policy,
)


def test_legacy_parity_matches_pz_semantics() -> None:
    agents = ["ops_0", "runner_0", "qc_0"]
    cfg = {
        "schedule_reward": 2.5,
        "throughput_reward": 1.0,
        "violation_penalty": 0.1,
        "blocked_penalty": 0.2,
    }
    # Manual mirror of historical block
    manual = {a: 0.0 for a in agents}
    accepted = "ops_0"
    manual[accepted] += 2.5
    for a in agents:
        manual[a] = 1.0  # throughput assigns
    for a in agents:
        manual[a] -= 0.1 * 3
        manual[a] -= 0.2 * 1
    via = apply_legacy_rewards(
        {a: 0.0 for a in agents},
        agents,
        cfg,
        accepted_schedule_agent=accepted,
        result_released=True,
        violation_count=3,
        blocked_count=1,
    )
    assert via == manual
    composer = RewardComposer(legacy_compat_policy())
    rewards, breakdown = composer.step_rewards(
        agents,
        cfg,
        accepted_schedule_agent=accepted,
        result_released=True,
        violation_count=3,
        blocked_count=1,
    )
    assert rewards == manual
    assert breakdown is None


def test_composition_determinism() -> None:
    policy = legacy_compat_policy()
    comps = {c: 0.0 for c in COMPONENT_VOCAB}
    comps["operational_success"] = 1.0
    comps["safety_violation_penalty"] = -0.5
    s1, v1 = compose_components(comps, policy)
    s2, v2 = compose_components(comps, policy)
    assert s1 == s2 == 0.5
    assert v1 == v2


def test_missing_component_fail_closed() -> None:
    policy = legacy_compat_policy()
    with pytest.raises(RewardCompositionError):
        compose_components({"operational_success": 1.0}, policy)


def test_envelope_validation() -> None:
    policy = legacy_compat_policy()
    comps = {c: 0.0 for c in COMPONENT_VOCAB}
    comps["operational_success"] = 1.0
    env = build_reward_evidence_envelope(
        envelope_id="ree-1",
        run_id="run-1",
        step=0,
        agent_id="ops_0",
        policy=policy,
        components=comps,
        scalar_reward=1.0,
        public_verifier_id="V_public.hospital_lab.v1",
        public_decision="accept",
    )
    assert env["artifact_kind"] == "RewardEvidenceEnvelope"
    assert env["claim_boundary"] == "simulation_research_only_no_clinical_validation"
    bad = copy.deepcopy(policy)
    bad["weights"] = {c: 1.0 for c in COMPONENT_VOCAB if c != "delay_cost"}
    bad.pop("policy_digest", None)
    with pytest.raises(RewardCompositionError):
        validate_composition_policy(bad)


def test_emit_component_breakdown_when_enabled() -> None:
    policy = legacy_compat_policy()
    policy = dict(policy)
    policy.pop("policy_digest", None)
    policy["emit_component_breakdown_in_info"] = True
    composer = RewardComposer(policy)
    rewards, breakdown = composer.step_rewards(
        ["ops_0"],
        {"throughput_reward": 1.0},
        accepted_schedule_agent=None,
        result_released=True,
        violation_count=0,
        blocked_count=0,
    )
    assert rewards["ops_0"] == 1.0
    assert breakdown is not None
    assert breakdown["ops_0"]["operational_success"] == 1.0
