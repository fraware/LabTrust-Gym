"""
Tests for gate evaluation (policy.gate_eval): PASS/FAIL/SKIP semantics.
No assume-pass; FAIL with evidence and SKIP with reason.
"""

from pathlib import Path
from typing import Any

from labtrust_gym.policy.gate_eval import (
    SKIP_REASON_NOT_APPLICABLE,
    evaluate_gate,
    load_gate_policy,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_gate_fail_with_evidence() -> None:
    """
    Rule attack_success_rate_zero with sec.attack_success_rate > 0 produces FAIL
    with evidence in rationale (no assume-pass).
    """
    repo_root = _repo_root()
    gate_policy = load_gate_policy(repo_root)
    nominal: dict[tuple[str, str], int] = {}
    row: dict[str, Any] = {
        "scale_id": "small_smoke",
        "method_id": "kernel_auction_whca_shielded",
        "injection_id": "INJ-ID-SPOOF-001",
        "sec.attack_success_rate": 0.5,
        "safety.violations_total": 0,
    }
    verdict, rationale = evaluate_gate(row, nominal, gate_policy)
    assert verdict == "FAIL"
    assert "0.5" in rationale or "attack_success_rate" in rationale


def test_gate_skip_with_reason() -> None:
    """
    Injection with no gate rule produces SKIP with reason not_applicable
    (no PASS for unimplemented or missing rule).
    """
    repo_root = _repo_root()
    gate_policy = load_gate_policy(repo_root)
    nominal: dict[tuple[str, str], int] = {}
    row: dict[str, Any] = {
        "scale_id": "small_smoke",
        "method_id": "kernel_auction_whca_shielded",
        "injection_id": "INJ-TIMING-QUEUE-001",
        "sec.attack_success_rate": None,
        "safety.violations_total": 0,
    }
    verdict, rationale = evaluate_gate(row, nominal, gate_policy)
    assert verdict == "SKIP"
    assert SKIP_REASON_NOT_APPLICABLE in rationale
