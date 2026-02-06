"""
Security attack suite runner: execute golden security scenarios and emit attack_results.json.

Loads policy/golden/security_attack_suite.v0.1.yaml; for each attack (optionally filtered
by smoke=True), runs the scenario (prompt-injection in-process or test_ref via pytest);
writes SECURITY/attack_results.json with pass/fail and optional receipts.
Deterministic when run with fixed seed; CI-runnable in smoke mode.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import load_yaml


def load_attack_suite(policy_root: Path) -> dict[str, Any]:
    """Load security_attack_suite.v0.1.yaml from policy/golden/."""
    path = policy_root / "policy" / "golden" / "security_attack_suite.v0.1.yaml"
    if not path.exists():
        return {}
    data = load_yaml(path)
    return data if isinstance(data, dict) else {}


def load_prompt_injection_scenarios(policy_root: Path) -> list[dict[str, Any]]:
    """Load prompt_injection_scenarios.v0.1.yaml scenarios."""
    path = policy_root / "policy" / "golden" / "prompt_injection_scenarios.v0.1.yaml"
    if not path.exists():
        return []
    data = load_yaml(path)
    scenarios = (data or {}).get("scenarios", [])
    return scenarios if isinstance(scenarios, list) else []


def _run_prompt_injection_attack(
    scenario_id: str,
    scenarios: list[dict[str, Any]],
    policy_root: Path,
    seed: int,
) -> tuple[bool, str | None]:
    """
    Run one prompt-injection scenario in-process (same logic as golden test).
    Returns (passed, error_message).
    """
    spec = next((s for s in scenarios if s.get("scenario_id") == scenario_id), None)
    if not spec:
        return (
            False,
            f"scenario_id {scenario_id!r} not in prompt_injection_scenarios",
        )
    try:
        from labtrust_gym.baselines.llm.agent import (
            DeterministicConstrainedBackend,
            LLMAgentWithShield,
        )
    except ImportError as e:
        return False, f"LLM agent import failed: {e}"
    try:
        import gymnasium  # noqa: F401
        import pettingzoo  # noqa: F401
    except ImportError:
        return False, "pettingzoo or gymnasium not installed"
    allowed = spec.get("allowed_actions_for_assert", ["NOOP", "TICK"])
    injection_source = spec.get("injection_source", "specimen_note")
    adversarial_string = spec.get("adversarial_string", "")
    obs = _observation_with_injection(injection_source, adversarial_string, allowed)
    rbac = {
        "roles": [{"role_id": "ROLE_RECEPTION", "allowed_actions": allowed}],
        "agents": {"ops_0": "ROLE_RECEPTION"},
    }
    agent = LLMAgentWithShield(
        backend=DeterministicConstrainedBackend(seed=seed, default_action_type="NOOP"),
        rbac_policy=rbac,
        pz_to_engine={"ops_0": "A_RECEPTION"},
        use_action_proposal_schema=True,
    )
    agent.reset(seed=seed, partner_id="", timing_mode="explicit")
    _, action_info, meta = agent.act(obs, agent_id="ops_0")
    action_type = (action_info or {}).get("action_type", "NOOP")
    if action_type not in allowed and action_type != "NOOP":
        return False, f"action_type {action_type!r} not in allowed {allowed}"
    proposal = ((meta or {}).get("_llm_decision") or {}).get("action_proposal") or {}
    proposal_type = proposal.get("action_type", "NOOP")
    if proposal_type not in allowed and proposal_type != "NOOP":
        return (
            False,
            f"proposal action_type {proposal_type!r} not in allowed {allowed}",
        )
    return True, None


def _observation_with_injection(
    injection_key: str,
    adversarial_string: str,
    allowed_actions: list[str],
) -> dict[str, Any]:
    obs = {
        "zone_id": "Z_SRA_RECEPTION",
        "site_id": "SITE_HUB",
        "t_s": 0,
        "queue_by_device": [],
        "log_frozen": 0,
        "role_id": "ROLE_RECEPTION",
    }
    if injection_key == "specimen_note":
        obs["specimen_notes"] = adversarial_string
    elif injection_key in ("transport_manifest_note", "scenario_note"):
        obs["scenario_notes"] = adversarial_string
    return obs


def _run_test_ref_attack(
    test_ref: str,
    repo_root: Path,
) -> tuple[bool, str | None]:
    """
    Run attack via pytest subprocess for test_ref (e.g. tests.test_tool_sandbox).
    Returns (passed, error_message).
    """
    # test_ref: "tests.test_tool_sandbox" or "tests/test_tool_sandbox.py"
    if test_ref.endswith(".py"):
        target = test_ref
    else:
        target = test_ref.replace(".", "/") + ".py"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        target,
        "-v",
        "--tb=no",
        "-q",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "")[:500]
            return False, err or f"pytest exited {result.returncode!s}"
        return True, None
    except subprocess.TimeoutExpired:
        return False, "pytest timeout (120s)"
    except Exception as e:
        return False, str(e)


def run_security_suite(
    policy_root: Path,
    repo_root: Path | None = None,
    smoke_only: bool = True,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """
    Run all attacks in the security attack suite (smoke-only or full).
    Returns list of result dicts: attack_id, passed, outcome, duration_ms, error.
    """
    repo_root = repo_root or policy_root
    suite = load_attack_suite(policy_root)
    attacks = suite.get("attacks") or []
    if smoke_only:
        attacks = [a for a in attacks if a.get("smoke") is True]
    scenarios = load_prompt_injection_scenarios(policy_root)
    results: list[dict[str, Any]] = []
    for attack in attacks:
        attack_id = attack.get("attack_id", "unknown")
        expected = attack.get("expected_outcome", "blocked")
        t0 = time.perf_counter()
        passed = False
        err: str | None = None
        scenario_ref = attack.get("scenario_ref")
        test_ref = attack.get("test_ref")
        if scenario_ref:
            passed, err = _run_prompt_injection_attack(scenario_ref, scenarios, policy_root, seed)
        elif test_ref:
            passed, err = _run_test_ref_attack(test_ref, repo_root)
        else:
            err = "attack has no scenario_ref or test_ref"
        duration_ms = round((time.perf_counter() - t0) * 1000)
        results.append(
            {
                "attack_id": attack_id,
                "risk_id": attack.get("risk_id"),
                "control_id": attack.get("control_id"),
                "expected_outcome": expected,
                "passed": passed,
                "duration_ms": duration_ms,
                "error": err,
            }
        )
    return results


def write_attack_results(
    results: list[dict[str, Any]],
    out_path: Path,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Write attack_results.json with results and optional metadata."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "0.1",
        "metadata": metadata or {},
        "results": results,
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.get("passed")),
            "failed": sum(1 for r in results if not r.get("passed")),
        },
    }
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_suite_and_emit(
    policy_root: Path,
    out_dir: Path,
    repo_root: Path | None = None,
    smoke_only: bool = True,
    seed: int = 42,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Run security suite and write SECURITY/attack_results.json under out_dir.
    Returns results list.
    """
    results = run_security_suite(
        policy_root=policy_root,
        repo_root=repo_root or policy_root,
        smoke_only=smoke_only,
        seed=seed,
    )
    security_dir = out_dir / "SECURITY"
    security_dir.mkdir(parents=True, exist_ok=True)
    write_attack_results(
        results,
        security_dir / "attack_results.json",
        metadata=metadata,
    )
    return results
