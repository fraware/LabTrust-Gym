"""
Security attack suite: smoke run is deterministic; attack_results.json has expected structure.
CI-runnable with smoke_only=True (default).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.security_runner import (
    load_attack_suite,
    run_security_suite,
    run_suite_and_emit,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_load_attack_suite() -> None:
    """Attack suite YAML loads; attacks have risk_id, control_id, scenario_ref or test_ref."""
    root = _repo_root()
    suite = load_attack_suite(root)
    assert isinstance(suite, dict)
    attacks = suite.get("attacks") or []
    assert len(attacks) >= 1
    for a in attacks:
        assert "attack_id" in a
        assert a.get("risk_id") or a.get("control_id")
        assert (
            a.get("scenario_ref") or a.get("test_ref") or a.get("llm_attacker")
        ), "each attack must have scenario_ref, test_ref, or llm_attacker"


def test_detector_attack_sec_detector_001_in_suite() -> None:
    """SEC-DETECTOR-001 exists in suite with test_ref and control_id CTRL-DETECTOR-ADVISOR."""
    root = _repo_root()
    suite = load_attack_suite(root)
    attacks = suite.get("attacks") or []
    detector = next(
        (a for a in attacks if a.get("attack_id") == "SEC-DETECTOR-001"), None
    )
    assert detector is not None, "SEC-DETECTOR-001 must be in security_attack_suite"
    assert detector.get("control_id") == "CTRL-DETECTOR-ADVISOR"
    assert detector.get("test_ref") == "tests.test_detector_advisor_taskh"
    assert detector.get("risk_id") == "R-COMMS-002"


def test_run_security_suite_smoke_deterministic() -> None:
    """Running suite twice with same seed yields same pass/fail and result count."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    root = _repo_root()
    results1 = run_security_suite(
        policy_root=root,
        repo_root=root,
        smoke_only=True,
        seed=99,
    )
    results2 = run_security_suite(
        policy_root=root,
        repo_root=root,
        smoke_only=True,
        seed=99,
    )
    assert len(results1) == len(results2)
    for r1, r2 in zip(results1, results2):
        assert r1["attack_id"] == r2["attack_id"]
        assert r1["passed"] == r2["passed"]


def test_run_suite_and_emit_writes_attack_results() -> None:
    """run_suite_and_emit creates SECURITY/attack_results.json with version, results, summary."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    root = _repo_root()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        results = run_suite_and_emit(
            policy_root=root,
            out_dir=out,
            repo_root=root,
            smoke_only=True,
            seed=42,
        )
        path = out / "SECURITY" / "attack_results.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("version") == "0.1"
        assert "results" in data
        assert "summary" in data
        assert data["summary"]["total"] == len(results)
        assert data["summary"]["passed"] + data["summary"]["failed"] == len(results)


@pytest.mark.security
def test_security_suite_smoke_gate_all_passed() -> None:
    """
    Regression gate: every smoke attack must pass (control held).
    Fails the build if any prompt-injection or test_ref attack in the smoke set
    does not meet its expected_outcome (blocked/detected).
    """
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    root = _repo_root()
    results = run_security_suite(
        policy_root=root,
        repo_root=root,
        smoke_only=True,
        seed=42,
        timeout_s=120,
    )
    assert len(results) >= 1, (
        "Security suite smoke must contain at least one attack; "
        "check policy/golden/security_attack_suite.v0.1.yaml"
    )
    failed = [r for r in results if not r.get("passed")]
    if failed:
        lines = [
            f"  {r.get('attack_id', '?')}: {r.get('error', 'no error')!r}"
            for r in failed
        ]
        raise AssertionError(
            f"Security suite smoke gate: {len(failed)} attack(s) did not pass.\n"
            + "\n".join(lines)
        )


@pytest.mark.security
@pytest.mark.live
@pytest.mark.skipif(
    not os.environ.get("LABTRUST_RUN_LLM_ATTACKER") or not os.environ.get("OPENAI_API_KEY"),
    reason="LABTRUST_RUN_LLM_ATTACKER=1 and OPENAI_API_KEY required for red-team regression",
)
def test_red_team_llm_attacker_regression() -> None:
    """
    Red-team regression: run all LLM-attacker attacks; every one must be blocked.
    Skipped unless LABTRUST_RUN_LLM_ATTACKER=1 and OPENAI_API_KEY are set.
    """
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    root = _repo_root()
    results = run_security_suite(
        policy_root=root,
        repo_root=root,
        smoke_only=False,
        seed=42,
        timeout_s=120,
        llm_attacker=True,
        allow_network=True,
        llm_backend="openai_live",
    )
    llm_results = [r for r in results if r.get("llm_attacker")]
    assert len(llm_results) >= 1, "Suite must define at least one LLM-attacker attack"
    failed = [r for r in llm_results if not r.get("passed")]
    if failed:
        lines = [
            f"  {r.get('attack_id', '?')}: {r.get('error', 'no error')!r}"
            for r in failed
        ]
        raise AssertionError(
            f"Red-team regression: {len(failed)} LLM-attacker attack(s) did not pass.\n"
            + "\n".join(lines)
        )
