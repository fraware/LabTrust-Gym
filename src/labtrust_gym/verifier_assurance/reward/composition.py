"""Reward decomposition and PCS RewardEvidenceEnvelope.v1."""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Mapping

from labtrust_gym.errors import PolicyLoadError
from labtrust_gym.policy.loader import load_json, validate_against_schema
from labtrust_gym.util.json_utils import canonical_json
from pathlib import Path

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"

COMPONENT_VOCAB = (
    "operational_success",
    "qc_compliance",
    "process_compliance",
    "authorization_compliance",
    "audit_integrity",
    "critical_result_handling",
    "resource_cost",
    "delay_cost",
    "side_effect_penalty",
    "safety_violation_penalty",
)

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[4]
    / "policy"
    / "schemas"
    / "verifier_assurance"
    / "RewardCompositionPolicy.v1.schema.json"
)
_ENVELOPE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[4]
    / "policy"
    / "schemas"
    / "pcs"
    / "RewardEvidenceEnvelope.v1.schema.json"
)


class RewardCompositionError(ValueError):
    """Fail-closed reward composition error."""


def compute_policy_digest(policy: dict[str, Any]) -> str:
    body = {k: v for k, v in policy.items() if k != "policy_digest"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def validate_composition_policy(policy: dict[str, Any]) -> dict[str, Any]:
    try:
        validate_against_schema(policy, load_json(_SCHEMA_PATH), path=_SCHEMA_PATH)
    except PolicyLoadError as exc:
        raise RewardCompositionError(str(exc)) from exc
    weights = policy.get("weights") or {}
    for name in policy.get("components") or []:
        if name not in weights:
            raise RewardCompositionError(f"missing weight for component: {name}")
    for name in weights:
        if name not in COMPONENT_VOCAB:
            raise RewardCompositionError(f"unknown component weight: {name}")
    out = copy.deepcopy(policy)
    digest = compute_policy_digest(out)
    declared = out.get("policy_digest")
    if declared is not None and declared != digest:
        raise RewardCompositionError("policy_digest mismatch")
    out["policy_digest"] = digest
    return out


def legacy_compat_policy() -> dict[str, Any]:
    """Policy that preserves pz_parallel legacy numeric behavior via shim mapping."""
    return validate_composition_policy(
        {
            "schema_id": "RewardCompositionPolicy.v1",
            "policy_id": "reward-compat-legacy-v1",
            "components": list(COMPONENT_VOCAB),
            "weights": {c: 1.0 for c in COMPONENT_VOCAB},
            "legacy_compat": {
                "enabled": True,
                "preserve_benchmark_numeric_behavior": True,
                "legacy_keys": [
                    "schedule_reward",
                    "throughput_reward",
                    "violation_penalty",
                    "blocked_penalty",
                ],
            },
            "emit_component_breakdown_in_info": False,
            "emit_step_evidence": False,
            "claim_boundary": CLAIM_BOUNDARY,
        }
    )


def compute_legacy_component_vector(
    reward_config: Mapping[str, Any],
    *,
    accepted_schedule: bool,
    result_released: bool,
    violation_count: int,
    blocked_count: int,
) -> dict[str, float]:
    """Map legacy reward_config outcomes into the named component vocabulary."""
    schedule_r = 0.0
    if reward_config.get("schedule_reward") and accepted_schedule:
        schedule_r = float(reward_config.get("schedule_reward", 0.0))
    throughput_r = 0.0
    if reward_config.get("throughput_reward") and result_released:
        throughput_r = float(reward_config.get("throughput_reward", 1.0))
    violation_p = 0.0
    if reward_config.get("violation_penalty"):
        violation_p = float(reward_config["violation_penalty"]) * violation_count
    blocked_p = 0.0
    if reward_config.get("blocked_penalty"):
        blocked_p = float(reward_config["blocked_penalty"]) * blocked_count
    return {
        "operational_success": schedule_r + throughput_r,
        "qc_compliance": 0.0,
        "process_compliance": 0.0,
        "authorization_compliance": 0.0,
        "audit_integrity": 0.0,
        "critical_result_handling": 0.0,
        "resource_cost": 0.0,
        "delay_cost": 0.0,
        "side_effect_penalty": 0.0,
        "safety_violation_penalty": -(violation_p + blocked_p),
    }


def apply_legacy_rewards(
    rewards: dict[str, float],
    agents: list[str],
    reward_config: Mapping[str, Any],
    *,
    accepted_schedule_agent: str | None,
    result_released: bool,
    violation_count: int,
    blocked_count: int,
) -> dict[str, float]:
    """Exact parity with pz_parallel reward block (throughput assigns, does not add)."""
    out = {a: float(rewards.get(a, 0.0)) for a in agents}
    if reward_config.get("schedule_reward") and accepted_schedule_agent:
        r = float(reward_config.get("schedule_reward", 0.0))
        out[accepted_schedule_agent] = out.get(accepted_schedule_agent, 0.0) + r
    if reward_config.get("throughput_reward") and result_released:
        for a in agents:
            # Historical behavior: assignment, not accumulation.
            out[a] = float(reward_config.get("throughput_reward", 1.0))
    if reward_config.get("violation_penalty"):
        p = float(reward_config["violation_penalty"])
        for a in agents:
            out[a] -= p * violation_count
    if reward_config.get("blocked_penalty"):
        p = float(reward_config["blocked_penalty"])
        for a in agents:
            out[a] -= p * blocked_count
    return out


def compose_components(
    components: Mapping[str, float],
    policy: Mapping[str, Any],
) -> tuple[float, dict[str, float]]:
    """Weighted sum; missing required component fail-closed."""
    validated = validate_composition_policy(dict(policy))
    weights = validated["weights"]
    vector: dict[str, float] = {}
    for name in validated["components"]:
        if name not in components:
            raise RewardCompositionError(f"missing component: {name}")
        vector[name] = float(components[name]) * float(weights[name])
    scalar = float(sum(vector.values()))
    return scalar, vector


def build_reward_evidence_envelope(
    *,
    envelope_id: str,
    run_id: str,
    step: int,
    agent_id: str,
    policy: Mapping[str, Any],
    components: Mapping[str, float],
    scalar_reward: float,
    public_verifier_id: str | None = None,
    public_decision: str | None = None,
) -> dict[str, Any]:
    validated = validate_composition_policy(dict(policy))
    for name in validated["components"]:
        if name not in components:
            raise RewardCompositionError(f"missing component for envelope: {name}")
    envelope = {
        "artifact_kind": "RewardEvidenceEnvelope",
        "version": "1",
        "envelope_id": envelope_id,
        "run_id": run_id,
        "step": int(step),
        "agent_id": agent_id,
        "composition_policy_id": validated["policy_id"],
        "composition_policy_digest": validated["policy_digest"],
        "components": {k: float(components[k]) for k in validated["components"]},
        "scalar_reward": float(scalar_reward),
        "public_verifier_id": public_verifier_id,
        "public_decision": public_decision,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    try:
        validate_against_schema(envelope, load_json(_ENVELOPE_SCHEMA_PATH), path=_ENVELOPE_SCHEMA_PATH)
    except PolicyLoadError as exc:
        raise RewardCompositionError(str(exc)) from exc
    return envelope


class RewardComposer:
    """Wraps legacy or decomposed reward composition."""

    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self._policy = validate_composition_policy(policy or legacy_compat_policy())

    @property
    def policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._policy)

    def step_rewards(
        self,
        agents: list[str],
        reward_config: Mapping[str, Any],
        *,
        accepted_schedule_agent: str | None,
        result_released: bool,
        violation_count: int,
        blocked_count: int,
        component_overrides: Mapping[str, Mapping[str, float]] | None = None,
    ) -> tuple[dict[str, float], dict[str, dict[str, float]] | None]:
        if self._policy["legacy_compat"]["enabled"] and self._policy["legacy_compat"][
            "preserve_benchmark_numeric_behavior"
        ]:
            rewards = apply_legacy_rewards(
                {a: 0.0 for a in agents},
                agents,
                reward_config,
                accepted_schedule_agent=accepted_schedule_agent,
                result_released=result_released,
                violation_count=violation_count,
                blocked_count=blocked_count,
            )
            breakdown = None
            if self._policy.get("emit_component_breakdown_in_info"):
                breakdown = {}
                for a in agents:
                    comps = {c: 0.0 for c in COMPONENT_VOCAB}
                    comps["operational_success"] = float(rewards[a])
                    comps["safety_violation_penalty"] = 0.0
                    breakdown[a] = comps
            return rewards, breakdown
        # Non-legacy path
        rewards: dict[str, float] = {}
        breakdown: dict[str, dict[str, float]] = {}
        for a in agents:
            comps = {c: 0.0 for c in self._policy["components"]}
            if component_overrides and a in component_overrides:
                comps.update({k: float(v) for k, v in component_overrides[a].items()})
            scalar, weighted = compose_components(comps, self._policy)
            rewards[a] = scalar
            breakdown[a] = weighted
        if not self._policy.get("emit_component_breakdown_in_info"):
            return rewards, None
        return rewards, breakdown
