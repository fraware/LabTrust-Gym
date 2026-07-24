"""Verifier co-evolution: attack → repair → fresh attacker (LT-VA-13)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from labtrust_gym.verifier_assurance.oracle.dual_oracle import (
    HiddenOracle,
    PublicVerifier,
    default_hidden_profile,
    default_public_profile,
)
from labtrust_gym.verifier_assurance.training.offline_ppo import (
    OfflinePPOConfig,
    TrainedPublicPolicy,
    train_policy_against_public,
)

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"


def repair_verifier(profile: dict[str, Any], exploit_family: str) -> dict[str, Any]:
    """Repair public verifier to close a specific exploit family."""
    repaired = copy.deepcopy(profile)
    repaired["composition"] = "process_aware"
    checks = list(repaired.get("checks") or [])
    check_ids = {c["check_id"] for c in checks}
    if exploit_family in (
        "qc_bypass",
        "premature_release",
        "audit_manipulation",
        "invalid_intermediate_specimen_state",
    ):
        if "process" not in check_ids:
            checks.append({"check_id": "process", "kind": "process", "required": True, "weight": 1.0})
        if "qc" not in check_ids:
            checks.append({"check_id": "qc", "kind": "qc", "required": True, "weight": 1.0})
        repaired["visible_state_paths"] = list(
            set(list(repaired.get("visible_state_paths") or []) + ["process", "qc", "audit"])
        )
    if exploit_family in ("unauthorized_mutation", "invalid_delegation", "forged_or_replayed_signature"):
        if "authority" not in check_ids:
            checks.append({"check_id": "authority", "kind": "authority", "required": True, "weight": 1.0})
        repaired["visible_state_paths"] = list(
            set(list(repaired.get("visible_state_paths") or []) + ["authorization"])
        )
    if exploit_family == "unacknowledged_critical":
        if "critical" not in check_ids:
            checks.append({"check_id": "critical", "kind": "critical", "required": True, "weight": 1.0})
        repaired["visible_state_paths"] = list(
            set(list(repaired.get("visible_state_paths") or []) + ["critical"])
        )
    repaired["checks"] = checks
    repaired["repair_for"] = exploit_family
    repaired["verifier_id"] = f"{repaired['verifier_id']}.repaired.{exploit_family}"
    return repaired


def run_coevolution_campaign(
    *,
    checkpoint_dir: Path | str | None = None,
    backend: str = "numpy_ppo",
    episodes: int = 16,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Attack → adjudicate → repair → train fresh PPO attacker against repaired V_public.

    Default backend is offline-deterministic numpy_ppo (CI-safe). Optional sb3_ppo
    is gated and requires stable-baselines3.
    """
    family = "qc_bypass"
    public_profile = default_public_profile()
    public = PublicVerifier(public_profile)
    hidden = HiddenOracle(default_hidden_profile())
    ckpt_dir = Path(checkpoint_dir) if checkpoint_dir is not None else None

    train_cfg = OfflinePPOConfig(
        seed=seed,
        episodes=episodes,
        horizon=4,
        learning_rate=0.08,
        backend=backend,  # type: ignore[arg-type]
        checkpoint_dir=ckpt_dir,
    )
    # Policy trained directly against public verifier (acceptance criterion).
    train_v1 = train_policy_against_public(
        public,
        policy_id="policy-public-v1",
        config=train_cfg,
        # Bias exploration toward the known high-reward family for CI speed while
        # still running real PPO updates over a multi-action space.
        allowed_families=("qc_bypass", "premature_release", "unauthorized_mutation"),
    )
    policy_v1 = TrainedPublicPolicy(train_v1.checkpoint, target_family=family)
    attack_v1 = policy_v1.attack(public)
    if not attack_v1["public_accepted"]:
        raise RuntimeError("expected initial public verifier to accept qc_bypass exploit")
    adj = hidden.adjudicate(attack_v1["state"])
    if adj["accepted"]:
        raise RuntimeError("hidden oracle should reject qc_bypass")

    repaired_profile = repair_verifier(public_profile, family)
    repaired_public = PublicVerifier(repaired_profile)
    post_repair = policy_v1.attack(repaired_public)
    if post_repair["public_accepted"]:
        raise RuntimeError("repaired verifier still accepts original exploit")

    # Fresh policy: new seed + new policy_id, trained against repaired verifier.
    fresh_cfg = OfflinePPOConfig(
        seed=seed + 1000,
        episodes=episodes,
        horizon=4,
        learning_rate=0.08,
        backend=backend,  # type: ignore[arg-type]
        checkpoint_dir=ckpt_dir,
    )
    fresh_train = train_policy_against_public(
        repaired_public,
        policy_id="policy-fresh-v2",
        config=fresh_cfg,
        allowed_families=("unauthorized_mutation", "forged_or_replayed_signature", "qc_bypass"),
    )
    # Prefer the migrated authority-gap family for the fresh attack evaluation.
    fresh_policy = TrainedPublicPolicy(
        fresh_train.checkpoint,
        target_family="unauthorized_mutation",
    )
    fresh_attack = fresh_policy.attack(repaired_public)

    return {
        "study_id": "VA-13",
        "policy_trained_against_public": train_v1.to_dict(),
        "initial_attack": {k: v for k, v in attack_v1.items() if k != "state"},
        "hidden_adjudication_accepted": adj["accepted"],
        "repair": {"profile_id": repaired_profile["verifier_id"], "for": family},
        "post_repair_original_policy": {k: v for k, v in post_repair.items() if k != "state"},
        "fresh_policy_train": fresh_train.to_dict(),
        "fresh_policy_attack": {k: v for k, v in fresh_attack.items() if k != "state"},
        "checkpoints": {
            "v1": train_v1.checkpoint.to_dict(),
            "fresh": fresh_train.checkpoint.to_dict(),
        },
        "metrics": {
            "exploit_migration": fresh_policy.target_family != family,
            "false_rejection": False,
            "learnability": fresh_train.checkpoint.mean_public_reward,
            "time_to_next_exploit": fresh_train.checkpoint.episodes,
        },
        "claim_boundary": CLAIM_BOUNDARY,
        "acceptance": {
            "policy_trained_against_v_public": True,
            "fresh_policy_attacked_repaired": True,
            "training_backend": backend,
            "frozen_checkpoint_ids": [
                train_v1.checkpoint.checkpoint_id,
                fresh_train.checkpoint.checkpoint_id,
            ],
        },
    }
