"""
Coordination red-team: success/detection/containment consistent; strict signatures
+ bus replay protection block INJ-ID-SPOOF-001, INJ-REPLAY-001.
"""

from __future__ import annotations

from labtrust_gym.baselines.adversary_coord import (
    RedTeamStrategy,
    evaluate_episode_outcome,
    get_definitions_for_strategy,
    get_injection_id_for_strategy,
)
from labtrust_gym.config import get_repo_root
from labtrust_gym.policy.loader import load_yaml


def test_red_team_definitions_consistent() -> None:
    """Every strategy has non-empty success, detection, containment definitions."""
    for strategy in RedTeamStrategy:
        defs = get_definitions_for_strategy(strategy)
        assert defs is not None, f"Missing definitions for {strategy}"
        assert defs.success_definition.strip(), f"Empty success_definition for {strategy}"
        assert defs.detection_definition.strip(), f"Empty detection_definition for {strategy}"
        assert defs.containment_definition.strip(), f"Empty containment_definition for {strategy}"


def test_strategy_to_injection_id_mapping() -> None:
    """Strategy maps to injection_id; identity/replay map to INJ-ID-SPOOF-001, INJ-REPLAY-001."""
    assert get_injection_id_for_strategy(RedTeamStrategy.IDENTITY_ROTATION) == "INJ-ID-SPOOF-001"
    assert get_injection_id_for_strategy(RedTeamStrategy.REPLAY_ATTEMPTS) == "INJ-REPLAY-001"
    assert get_injection_id_for_strategy(RedTeamStrategy.COLLUSION) == "INJ-COLLUSION-001"
    for strategy in RedTeamStrategy:
        iid = get_injection_id_for_strategy(strategy)
        assert iid, f"Strategy {strategy} must map to an injection_id"


def test_injections_v02_yaml_loaded_and_consistent() -> None:
    """injections.v0.2.yaml exists, version 0.2, each entry has success/detection/containment."""
    root = get_repo_root()
    path = root / "policy" / "coordination" / "injections.v0.2.yaml"
    assert path.exists(), "policy/coordination/injections.v0.2.yaml must exist"
    data = load_yaml(path)
    assert data.get("version") == "0.2"
    injections = data.get("injections") or []
    assert injections, "injections.v0.2.yaml must list at least one injection"
    for inj in injections:
        assert inj.get("injection_id"), "Each injection must have injection_id"
        assert inj.get("success_definition"), "success_definition required"
        assert inj.get("detection_definition"), "detection_definition required"
        assert inj.get("containment_definition"), "containment_definition required"


def test_evaluate_episode_outcome_stealth_success() -> None:
    """stealth_success True only when attack_success and not detected."""
    out = evaluate_episode_outcome(
        attack_success=True,
        first_detection_step=None,
        first_containment_step=None,
        first_application_step=10,
    )
    assert out["success"] is True
    assert out["detected"] is False
    assert out["stealth_success"] is True

    out2 = evaluate_episode_outcome(
        attack_success=True,
        first_detection_step=5,
        first_containment_step=6,
        first_application_step=2,
    )
    assert out2["success"] is True
    assert out2["detected"] is True
    assert out2["stealth_success"] is False

    out3 = evaluate_episode_outcome(
        attack_success=False,
        first_detection_step=3,
        first_containment_step=4,
        first_application_step=2,
    )
    assert out3["success"] is False
    assert out3["contained"] is True
    assert out3["stealth_success"] is False


def test_strict_signatures_and_replay_protection_block_injection_ids() -> None:
    """INJ-ID-SPOOF-001, INJ-REPLAY-001 defined with containment stating blocked/rejected."""
    root = get_repo_root()
    path = root / "policy" / "coordination" / "injections.v0.2.yaml"
    data = load_yaml(path)
    injections = {i["injection_id"]: i for i in (data.get("injections") or [])}
    for required_id in ("INJ-ID-SPOOF-001", "INJ-REPLAY-001"):
        assert required_id in injections, f"{required_id} in injections.v0.2.yaml"
        cont = (injections[required_id].get("containment_definition") or "").lower()
        assert "block" in cont or "reject" in cont or "rejected" in cont, (
            f"{required_id} containment_definition must state blocked/rejected"
        )


def test_red_team_injection_ids_in_registry() -> None:
    """All adversary_coord injection_ids are in the risk injector registry."""
    from labtrust_gym.security.risk_injections import INJECTION_REGISTRY

    for strategy in RedTeamStrategy:
        iid = get_injection_id_for_strategy(strategy)
        assert iid in INJECTION_REGISTRY, f"{iid} for {strategy} must be in INJECTION_REGISTRY"


def test_coordination_study_aggregate_includes_red_team_metrics() -> None:
    """Coordination study summary includes sec.stealth_success_rate, time_to_attribution_steps, blast_radius_proxy."""
    from labtrust_gym.studies.coordination_study_runner import _aggregate_cell_metrics

    episodes = [
        {
            "metrics": {
                "throughput": 2,
                "violations_by_invariant_id": {},
                "blocked_by_reason_code": {},
                "sec": {
                    "attack_success_rate": 0.0,
                    "stealth_success_rate": 0.0,
                    "time_to_attribution_steps": 5,
                    "blast_radius_proxy": 1,
                },
                "robustness": {"resilience_score": 0.8},
            },
        },
        {
            "metrics": {
                "throughput": 3,
                "violations_by_invariant_id": {},
                "blocked_by_reason_code": {},
                "sec": {
                    "attack_success_rate": 0.0,
                    "stealth_success_rate": 0.0,
                    "time_to_attribution_steps": 10,
                    "blast_radius_proxy": 2,
                },
                "robustness": {"resilience_score": 0.7},
            },
        },
    ]
    out = _aggregate_cell_metrics(episodes)
    assert "sec.stealth_success_rate" in out
    assert "sec.time_to_attribution_steps" in out
    assert "sec.blast_radius_proxy" in out
    assert out["sec.time_to_attribution_steps"] == 7.5
    assert out["sec.blast_radius_proxy"] == 1.5
