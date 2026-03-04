"""
Tests for gate evaluation (policy.gate_eval): PASS/FAIL/SKIP semantics.
No assume-pass; FAIL with evidence and SKIP with reason.
Table-driven tests use fixtures under tests/fixtures/gate_eval_vectors/.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from labtrust_gym.policy.gate_eval import (
    SKIP_REASON_NOT_APPLICABLE,
    evaluate_gate,
    load_gate_policy,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _gate_eval_vector_files() -> list[Path]:
    """All JSON vector files under gate_eval_vectors (pass/fail/boundary per rule type)."""
    root = _repo_root() / "tests" / "fixtures" / "gate_eval_vectors"
    if not root.is_dir():
        return []
    out: list[Path] = []
    for sub in root.iterdir():
        if sub.is_dir():
            for f in sub.glob("*.json"):
                out.append(f)
    return sorted(out)


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
    (no PASS for unimplemented or missing rule). Use an injection_id not in the
    real gate policy so the test does not depend on which rules are configured.
    """
    repo_root = _repo_root()
    gate_policy = load_gate_policy(repo_root)
    nominal: dict[tuple[str, str], int] = {}
    row: dict[str, Any] = {
        "scale_id": "small_smoke",
        "method_id": "kernel_auction_whca_shielded",
        "injection_id": "INJ-NO-RULE-001",
        "sec.attack_success_rate": None,
        "safety.violations_total": 0,
    }
    verdict, rationale = evaluate_gate(row, nominal, gate_policy)
    assert verdict == "SKIP"
    assert SKIP_REASON_NOT_APPLICABLE in rationale


@pytest.mark.parametrize("vector_path", _gate_eval_vector_files(), ids=lambda p: str(p.relative_to(_repo_root())))
def test_gate_eval_vector(vector_path: Path) -> None:
    """
    Table-driven gate eval: each vector JSON defines row, gate_rules, nominal_by_scale_method,
    expected_verdict, and optional expected_rationale_substring. Asserts evaluate_gate outcome.
    """
    root = _repo_root()
    data = json.loads(vector_path.read_text(encoding="utf-8"))
    row = data["row"]
    gate_rules = data.get("gate_rules") or []
    gate_policy = {"version": "0.1", "rules": gate_rules}
    nominal_raw = data.get("nominal_by_scale_method") or {}
    nominal: dict[tuple[str, str], int] = {}
    for k, v in nominal_raw.items():
        if "|" in k:
            a, b = k.split("|", 1)
            nominal[(a, b)] = int(v)
        else:
            nominal[(k, "")] = int(v)
    expected_verdict = data["expected_verdict"]
    expected_sub = data.get("expected_rationale_substring")

    verdict, rationale = evaluate_gate(row, nominal, gate_policy)
    assert verdict == expected_verdict, f"vector={vector_path.name} rationale={rationale!r}"
    if expected_sub:
        assert expected_sub in rationale, (
            f"vector={vector_path.name} expected substring {expected_sub!r} in {rationale!r}"
        )
