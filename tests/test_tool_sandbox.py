"""
Tests for tool sandbox: deny-by-default egress, byte/record caps, data classification.

- Exfil attempt (egress_to non-allowlisted) blocked with TOOL_EGRESS_DENIED.
- Exceeding caps yields TOOL_EGRESS_LIMIT_EXCEEDED.
- Data class violation (PII/PHI not allowed) yields TOOL_DATA_CLASS_VIOLATION.
- Violations appear in step results and in episode metrics / receipts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.benchmarks.metrics import compute_episode_metrics
from labtrust_gym.tools.sandbox import (
    TOOL_DATA_CLASS_VIOLATION,
    TOOL_EGRESS_DENIED,
    TOOL_EGRESS_LIMIT_EXCEEDED,
    ToolSandbox,
    check_output_with_policy,
    load_tool_boundary_policy,
)
from labtrust_gym.tools.execution import execute_tool_safely


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def boundary_policy(repo_root: Path) -> dict:
    """Load boundary policy from repo (may be empty if file missing)."""
    return load_tool_boundary_policy(repo_root)


def test_exfil_attempt_blocked_tool_egress_denied(boundary_policy: dict) -> None:
    """Output with egress_to non-allowlisted endpoint -> TOOL_EGRESS_DENIED."""
    if not boundary_policy:
        pytest.skip("tool_boundary_policy.v0.1.yaml not found")
    sandbox = ToolSandbox(
        policy_root=None,
        tool_id="read_lims_v1",
        role_id="ROLE_ANALYTICS",
        boundary_policy=boundary_policy,
    )
    result = {"data": "ok", "egress_to": "http://exfil.example.com"}
    allowed, reason_code, details = sandbox.check_output(result)
    assert allowed is False
    assert reason_code == TOOL_EGRESS_DENIED
    assert details is not None
    assert details.get("egress_key") == "egress_to"
    assert (
        "exfil" in details.get("destination", "").lower()
        or "example" in details.get("destination", "").lower()
    )


def test_egress_internal_allowed(boundary_policy: dict) -> None:
    """Output with egress_to 'internal' is allowed."""
    if not boundary_policy:
        pytest.skip("tool_boundary_policy.v0.1.yaml not found")
    sandbox = ToolSandbox(
        policy_root=None,
        tool_id="read_lims_v1",
        role_id="ROLE_ANALYTICS",
        boundary_policy=boundary_policy,
    )
    result = {"data": "ok", "egress_to": "internal"}
    allowed, reason_code, _ = sandbox.check_output(result)
    assert allowed is True
    assert reason_code is None


def test_caps_exceeded_bytes_tool_egress_limit_exceeded(boundary_policy: dict) -> None:
    """Output exceeding max_bytes_out yields TOOL_EGRESS_LIMIT_EXCEEDED."""
    if not boundary_policy:
        pytest.skip("tool_boundary_policy.v0.1.yaml not found")
    # Default or read_lims has max_bytes_out 8192; use a tool with small limit from policy
    sandbox = ToolSandbox(
        policy_root=None,
        tool_id="write_lims_v1",
        role_id="ROLE_ANALYTICS",
        boundary_policy=boundary_policy,
    )
    # write_lims_v1 has max_bytes_out: 2048
    result = {"payload": "x" * 3000}
    allowed, reason_code, details = sandbox.check_output(result)
    assert allowed is False
    assert reason_code == TOOL_EGRESS_LIMIT_EXCEEDED
    assert details is not None
    assert details.get("limit") == "max_bytes_out"
    assert details.get("actual_bytes", 0) > details.get("max_bytes_out", 0)


def test_caps_exceeded_records_tool_egress_limit_exceeded(
    boundary_policy: dict,
) -> None:
    """Output exceeding max_records_out (list length) yields TOOL_EGRESS_LIMIT_EXCEEDED."""
    if not boundary_policy:
        pytest.skip("tool_boundary_policy.v0.1.yaml not found")
    # query_queue_v1 has max_records_out: 50; default 100. Use default by using a tool_id with low limit
    policy = dict(boundary_policy)
    policy.setdefault("tools", [])
    policy["tools"] = list(policy["tools"]) + [
        {
            "tool_id": "small_cap_tool",
            "max_bytes_out": 10000,
            "max_records_out": 5,
            "allowed_egress_endpoints": ["internal"],
            "output_classification": {"allowed_classes": ["Operational"]},
        }
    ]
    sandbox = ToolSandbox(
        policy_root=None,
        tool_id="small_cap_tool",
        role_id="ROLE_ANALYTICS",
        boundary_policy=policy,
    )
    result = {"items": list(range(10))}
    allowed, reason_code, details = sandbox.check_output(result)
    assert allowed is False
    assert reason_code == TOOL_EGRESS_LIMIT_EXCEEDED
    assert details is not None
    assert details.get("limit") == "max_records_out"
    assert details.get("actual_records", 0) == 10
    assert details.get("max_records_out", 0) == 5


def test_data_class_violation_phi_not_allowed(boundary_policy: dict) -> None:
    """Output containing PHI when tool only allows Operational -> TOOL_DATA_CLASS_VIOLATION."""
    if not boundary_policy:
        pytest.skip("tool_boundary_policy.v0.1.yaml not found")
    # write_lims_v1 has allowed_classes: ["Operational"] only
    sandbox = ToolSandbox(
        policy_root=None,
        tool_id="write_lims_v1",
        role_id="ROLE_ANALYTICS",
        boundary_policy=boundary_policy,
    )
    result = {"patient_id": "P123", "status": "ok"}
    # classification_rules map patient_id -> PHI
    allowed, reason_code, details = sandbox.check_output(result)
    assert allowed is False
    assert reason_code == TOOL_DATA_CLASS_VIOLATION
    assert details is not None
    assert details.get("data_class") == "PHI"


def test_data_class_operational_allowed(boundary_policy: dict) -> None:
    """Output with only Operational and allowed PHI (read_lims allows PHI) passes."""
    if not boundary_policy:
        pytest.skip("tool_boundary_policy.v0.1.yaml not found")
    sandbox = ToolSandbox(
        policy_root=None,
        tool_id="read_lims_v1",
        role_id="ROLE_ANALYTICS",
        boundary_policy=boundary_policy,
    )
    result = {"accession_id": "A1", "patient_id": "P1"}
    allowed, reason_code, _ = sandbox.check_output(result)
    assert allowed is True
    assert reason_code is None


def test_execute_tool_safely_sandbox_egress_denied(repo_root: Path) -> None:
    """execute_tool_safely with sandbox: egress denial returns (False, result, tool_error)."""
    policy = load_tool_boundary_policy(repo_root)
    if not policy:
        pytest.skip("tool_boundary_policy.v0.1.yaml not found")

    def adapter(tool_id: str, args: dict) -> dict:
        return {"egress_to": "http://evil.com", "data": "exfil"}

    sandbox = ToolSandbox(
        policy_root=repo_root,
        tool_id="read_lims_v1",
        role_id="ROLE_ANALYTICS",
        boundary_policy=policy,
    )
    ok, result, tool_error = execute_tool_safely(
        "read_lims_v1",
        {},
        adapter=adapter,
        sandbox_ctx={"sandbox": sandbox},
    )
    assert ok is False
    assert tool_error is not None
    assert tool_error.get("reason_code") == TOOL_EGRESS_DENIED
    assert result.get("egress_to") == "http://evil.com"


def test_violations_in_step_result_and_metrics(boundary_policy: dict) -> None:
    """Sandbox violation produces step result with violations/emits; metrics aggregate them."""
    if not boundary_policy:
        pytest.skip("tool_boundary_policy.v0.1.yaml not found")
    sandbox = ToolSandbox(
        policy_root=None,
        tool_id="write_lims_v1",
        role_id="ROLE_ANALYTICS",
        boundary_policy=boundary_policy,
    )
    result = {"patient_id": "P1"}
    allowed, reason_code, details = sandbox.check_output(result)
    assert allowed is False
    assert reason_code == TOOL_DATA_CLASS_VIOLATION
    # Simulate step result as engine would produce
    step_result = {
        "status": "BLOCKED",
        "blocked_reason_code": reason_code,
        "violations": [
            {
                "invariant_id": reason_code,
                "status": "VIOLATION",
                "reason_code": reason_code,
            }
        ],
        "emits": [reason_code],
    }
    metrics = compute_episode_metrics([[step_result]])
    assert "violations_by_invariant_id" in metrics
    assert metrics["violations_by_invariant_id"].get(TOOL_DATA_CLASS_VIOLATION) == 1


def test_check_output_with_policy_one_shot(repo_root: Path) -> None:
    """check_output_with_policy loads policy and checks in one call."""
    allowed, reason_code, details = check_output_with_policy(
        {"egress_to": "http://bad"},
        tool_id="read_lims_v1",
        policy_root=repo_root,
    )
    if reason_code is None and details is None:
        pytest.skip("no boundary policy in repo")
    assert allowed is False
    assert reason_code == TOOL_EGRESS_DENIED


def test_engine_sandbox_blocks_egress_in_step(repo_root: Path) -> None:
    """Full engine step: adapter returns egress_to external -> BLOCKED, TOOL_EGRESS_DENIED."""
    from labtrust_gym.engine.core_env import CoreEnv

    if not (repo_root / "policy" / "tool_boundary_policy.v0.1.yaml").exists():
        pytest.skip("tool_boundary_policy.v0.1.yaml not found")
    registry = {
        "tool_registry": {
            "version": "0.1",
            "tools": [
                {
                    "tool_id": "read_lims_v1",
                    "publisher": "labtrust",
                    "version": "0.1.0",
                    "capabilities": ["lims.read"],
                    "risk_class": "low",
                    "arg_schema_ref": "tool_args/read_lims_v1.args.v0.1.schema.json",
                },
            ],
        },
    }
    initial_state = {
        "effective_policy": {},
        "agents": [{"agent_id": "A_OPS_0", "zone_id": "Z_MAIN"}],
        "zone_layout": {
            "zones": [{"zone_id": "Z_MAIN"}],
            "graph_edges": [],
            "doors": [],
            "device_placement": {},
        },
        "specimens": [],
        "tokens": [],
        "audit_fault_injection": None,
        "tool_registry": registry,
        "policy_root": str(repo_root),
        "allowed_tools": ["read_lims_v1"],
        "tool_adapter": lambda tid, args: {
            "egress_to": "http://exfil.example.com",
            "data": "x",
        },
    }
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=99)
    event = {
        "t_s": 10,
        "agent_id": "A_OPS_0",
        "action_type": "INVOKE_TOOL",
        "args": {"accession_id": "ACC001"},
        "tool_id": "read_lims_v1",
    }
    result = env.step(event)
    assert result.get("status") == "BLOCKED"
    assert result.get("blocked_reason_code") == TOOL_EGRESS_DENIED
    violations = result.get("violations") or []
    assert any(v.get("reason_code") == TOOL_EGRESS_DENIED for v in violations)
    assert TOOL_EGRESS_DENIED in (result.get("emits") or [])
