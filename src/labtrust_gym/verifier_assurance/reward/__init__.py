"""Reward package."""

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

__all__ = [
    "COMPONENT_VOCAB",
    "RewardComposer",
    "RewardCompositionError",
    "apply_legacy_rewards",
    "build_reward_evidence_envelope",
    "compose_components",
    "legacy_compat_policy",
    "validate_composition_policy",
]
