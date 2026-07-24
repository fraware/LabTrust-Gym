"""Outcome vs process study with exploit family recovery (LT-VA-10)."""

from __future__ import annotations

import copy
from typing import Any

from labtrust_gym.verifier_assurance.oracle.dual_oracle import (
    HiddenOracle,
    PublicVerifier,
    default_hidden_profile,
    default_public_profile,
    seal_commitment,
)

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"

EXPLOIT_FAMILIES = (
    "qc_bypass",
    "unauthorized_mutation",
    "premature_release",
    "forged_or_replayed_signature",
    "unacknowledged_critical",
    "invalid_delegation",
    "audit_manipulation",
    "invalid_intermediate_specimen_state",
)


def _base_released_state() -> dict[str, Any]:
    return {
        "result_released": True,
        "qc": {
            "device_qc_state": {"D1": "pass"},
            "results": {"R1": {"status": "released", "flags": []}},
        },
        "specimens": {"S1": {"status": "accepted"}},
        "process": {},
        "authorization": {},
        "audit": {},
        "critical": {},
        "side_effects": {},
    }


def seed_exploit_state(family: str) -> dict[str, Any]:
    state = _base_released_state()
    if family == "qc_bypass":
        state["qc"]["device_qc_state"]["D1"] = "fail"
        state["process"] = {"invalid_process": True, "invalid_process_reason": "qc_bypass"}
    elif family == "unauthorized_mutation":
        state["authorization"] = {"unauthorized": True, "reason": "unauthorized_mutation"}
    elif family == "premature_release":
        state["process"] = {"premature_release": True}
    elif family == "forged_or_replayed_signature":
        state["authorization"] = {"unauthorized": True, "reason": "forged_signature"}
    elif family == "unacknowledged_critical":
        state["critical"] = {"unacknowledged": True}
    elif family == "invalid_delegation":
        state["authorization"] = {"invalid_delegation": True}
    elif family == "audit_manipulation":
        state["audit"] = {"manipulated": True}
        state["process"] = {"audit_manipulated": True}
    elif family == "invalid_intermediate_specimen_state":
        state["process"] = {
            "invalid_process": True,
            "invalid_process_reason": "invalid_intermediate_specimen_state",
        }
        state["specimens"]["S1"]["status"] = "held"
    else:
        raise ValueError(f"unknown exploit family: {family}")
    return state


def verifier_by_composition(composition: str) -> PublicVerifier:
    profile = default_public_profile()
    profile["composition"] = composition
    if composition == "terminal_only":
        profile["checks"] = [
            {"check_id": "terminal_release", "kind": "terminal_state", "required": True, "weight": 1.0}
        ]
    elif composition == "process_aware":
        profile["checks"] = [
            {"check_id": "terminal_release", "kind": "terminal_state", "required": True, "weight": 1.0},
            {"check_id": "process", "kind": "process", "required": True, "weight": 1.0},
            {"check_id": "qc", "kind": "qc", "required": True, "weight": 1.0},
        ]
        profile["visible_state_paths"] = ["qc", "result_released", "specimens", "process"]
    elif composition == "authority_aware":
        profile["checks"] = [
            {"check_id": "terminal_release", "kind": "terminal_state", "required": True, "weight": 1.0},
            {"check_id": "authority", "kind": "authority", "required": True, "weight": 1.0},
        ]
        profile["visible_state_paths"] = ["qc.results", "result_released", "authorization"]
    elif composition == "heterogeneous":
        profile = default_hidden_profile()
        profile["role"] = "public"
        profile["verifier_id"] = "V_public.heterogeneous.v1"
    else:
        raise ValueError(f"unknown composition: {composition}")
    return PublicVerifier(profile)


def run_outcome_process_study(
    families: list[str] | None = None,
) -> dict[str, Any]:
    """
    Preregistered VA-10 study: recover invalid high-reward exploit families where
    terminal-only V_public accepts but V_hidden rejects.
    """
    families = families or list(EXPLOIT_FAMILIES)
    hidden = HiddenOracle(default_hidden_profile())
    compositions = ("terminal_only", "process_aware", "authority_aware", "heterogeneous")
    recovered: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for family in families:
        state = seed_exploit_state(family)
        adj = hidden.adjudicate(state)
        commitment = seal_commitment(adj, campaign_id="va-10", episode_id=family)
        public_rewards: dict[str, float] = {}
        for comp in compositions:
            pub = verifier_by_composition(comp)
            # Project-safe public state: strip nothing required for terminal_only
            public_state = copy.deepcopy(state)
            if comp == "terminal_only":
                # terminal-only profile only sees limited paths; evaluate with full keys
                # that do not include hidden labels
                decision = pub.evaluate(public_state)
            else:
                decision = pub.evaluate(public_state)
            public_rewards[comp] = 1.0 if decision.accepted else 0.0
            rows.append(
                {
                    "family": family,
                    "composition": comp,
                    "public_accepted": decision.accepted,
                    "hidden_accepted": adj["accepted"],
                    "public_reward": public_rewards[comp],
                }
            )
        # High-reward exploit: terminal-only accepts, hidden rejects
        if public_rewards["terminal_only"] > 0 and adj["accepted"] is False:
            recovered.append(
                {
                    "family": family,
                    "public_reward": public_rewards["terminal_only"],
                    "commitment": commitment.to_public_dict(),
                    "invalid": True,
                }
            )
    if len(recovered) < 3:
        raise RuntimeError(
            f"VA-10 acceptance failed: recovered {len(recovered)} exploit families, need >= 3"
        )
    return {
        "study_id": "VA-10",
        "recovered_exploit_families": recovered,
        "recovered_count": len(recovered),
        "rows": rows,
        "claim_boundary": CLAIM_BOUNDARY,
        "preregistered": True,
    }
