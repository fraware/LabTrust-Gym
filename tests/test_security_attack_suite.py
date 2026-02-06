"""
Security attack suite: smoke run is deterministic; attack_results.json has expected structure.
CI-runnable with smoke_only=True (default).
"""

from __future__ import annotations

import json
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
        assert a.get("scenario_ref") or a.get("test_ref")


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
