"""Unit tests for attack evidence contract merge/resolution (LTG-PR5)."""

from __future__ import annotations

from labtrust_gym.policy.attack_evidence import (
    merge_evidence_contract,
    resolve_suite_evidence_contracts,
    validate_resolved_evidence_contracts,
)


def test_merge_evidence_contract_layers_and_budget() -> None:
    merged = merge_evidence_contract(
        {"residual_risk": "default", "budget": {"mode": "offline_fixed", "requires_live_llm": False}},
        {
            "threat_model": "tm",
            "attacker_capability": "cap",
            "success_condition": "sc",
            "baseline": "b",
            "optimized_attack": "o",
            "expected_detection_point": "d",
            "budget": {"max_rounds": 2},
        },
        {"reproducible_fixture": "fixture#1", "budget": {"notes": "n"}},
    )
    assert merged["threat_model"] == "tm"
    assert merged["residual_risk"] == "default"
    assert merged["reproducible_fixture"] == "fixture#1"
    assert merged["budget"]["mode"] == "offline_fixed"
    assert merged["budget"]["max_rounds"] == 2
    assert merged["budget"]["notes"] == "n"
    assert merged["budget"]["requires_live_llm"] is False


def test_smoke_live_llm_rejected() -> None:
    suite = {
        "attacks": [
            {
                "attack_id": "SEC-BAD-SMOKE",
                "smoke": True,
                "llm_attacker": True,
                "evidence_contract": {
                    "threat_model": "t",
                    "attacker_capability": "a",
                    "success_condition": "s",
                    "budget": {"mode": "live_llm_opt_in", "requires_live_llm": True},
                    "baseline": "b",
                    "optimized_attack": "o",
                    "expected_detection_point": "d",
                    "residual_risk": "r",
                    "reproducible_fixture": "f",
                },
            }
        ]
    }
    resolved = resolve_suite_evidence_contracts(suite)
    errs = validate_resolved_evidence_contracts(resolved)
    assert any("smoke=true" in e for e in errs)
