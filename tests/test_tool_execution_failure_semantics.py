"""
Tests for tool execution safety wrapper and canonical failure semantics.

- Adapter raises -> BLOCKED with TOOL_EXEC_EXCEPTION.
- Tool returns malformed output -> BLOCKED with TOOL_OUTPUT_MALFORMED.
- Timeout simulated -> BLOCKED with TOOL_TIMEOUT.
- Benchmark runner completes without uncaught exceptions.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.tools.execution import (
    TOOL_EXEC_EXCEPTION,
    TOOL_OUTPUT_MALFORMED,
    TOOL_TIMEOUT,
    execute_tool_safely,
)
from labtrust_gym.tools.registry import load_tool_registry


def _minimal_initial_state(
    registry: dict,
    policy_root: Path | None = None,
    tool_adapter=None,
    tool_timeout_s: float | None = None,
) -> dict:
    """Minimal initial_state for CoreEnv; optional tool_adapter, tool_timeout_s."""
    state = {
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
    }
    if policy_root is not None:
        state["policy_root"] = policy_root
    if tool_adapter is not None:
        state["tool_adapter"] = tool_adapter
    if tool_timeout_s is not None:
        state["tool_timeout_s"] = tool_timeout_s
    return state


@pytest.fixture
def repo_registry_and_root():
    """Load real tool registry and repo root."""
    from labtrust_gym.config import get_repo_root

    root = Path(get_repo_root())
    registry = load_tool_registry(root)
    if not registry.get("tool_registry", {}).get("tools"):
        pytest.skip("policy/tool_registry.v0.1.yaml has no tools")
    return registry, root


def test_tool_adapter_raises_exception_blocked_with_tool_exec_exception(
    repo_registry_and_root,
) -> None:
    """When the tool adapter raises, step returns BLOCKED with TOOL_EXEC_EXCEPTION."""
    registry, policy_root = repo_registry_and_root

    def failing_adapter(tool_id: str, args: dict):
        raise RuntimeError("simulated tool failure")

    initial_state = _minimal_initial_state(registry, policy_root=policy_root, tool_adapter=failing_adapter)
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 0,
        "agent_id": "A_OPS_0",
        "action_type": "TICK",
        "args": {"accession_id": "ACC001"},
        "tool_id": "read_lims_v1",
    }
    result = env.step(event)
    assert result.get("status") == "BLOCKED"
    assert result.get("blocked_reason_code") == TOOL_EXEC_EXCEPTION
    assert result.get("violations")
    violations = result.get("violations") or []
    violation = next(
        (v for v in violations if v.get("invariant_id") == "TOOL_EXEC_SAFETY"),
        None,
    )
    assert violation is not None
    assert violation.get("reason_code") == TOOL_EXEC_EXCEPTION
    assert TOOL_EXEC_EXCEPTION in result.get("emits", [])


def test_tool_returns_malformed_output_blocked_with_tool_output_malformed(
    repo_registry_and_root,
) -> None:
    """Tool returns non-dict -> BLOCKED with TOOL_OUTPUT_MALFORMED."""

    def malformed_adapter(tool_id: str, args: dict):
        return "not a dict"

    registry, policy_root = repo_registry_and_root
    initial_state = _minimal_initial_state(registry, policy_root=policy_root, tool_adapter=malformed_adapter)
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 0,
        "agent_id": "A_OPS_0",
        "action_type": "TICK",
        "args": {"accession_id": "ACC001"},
        "tool_id": "read_lims_v1",
    }
    result = env.step(event)
    assert result.get("status") == "BLOCKED"
    assert result.get("blocked_reason_code") == TOOL_OUTPUT_MALFORMED
    violations = result.get("violations") or []
    violation = next(
        (v for v in violations if v.get("invariant_id") == "TOOL_EXEC_SAFETY"),
        None,
    )
    assert violation is not None
    assert violation.get("reason_code") == TOOL_OUTPUT_MALFORMED
    assert TOOL_OUTPUT_MALFORMED in result.get("emits", [])


def test_tool_timeout_simulated_blocked_with_tool_timeout(
    repo_registry_and_root,
) -> None:
    """Adapter exceeds timeout -> BLOCKED with TOOL_TIMEOUT."""

    def slow_adapter(tool_id: str, args: dict):
        time.sleep(2.0)
        return {}

    registry, policy_root = repo_registry_and_root
    initial_state = _minimal_initial_state(
        registry,
        policy_root=policy_root,
        tool_adapter=slow_adapter,
        tool_timeout_s=0.1,
    )
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 0,
        "agent_id": "A_OPS_0",
        "action_type": "TICK",
        "args": {"accession_id": "ACC001"},
        "tool_id": "read_lims_v1",
    }
    result = env.step(event)
    assert result.get("status") == "BLOCKED"
    assert result.get("blocked_reason_code") == TOOL_TIMEOUT
    violations = result.get("violations") or []
    violation = next(
        (v for v in violations if v.get("invariant_id") == "TOOL_EXEC_SAFETY"),
        None,
    )
    assert violation is not None
    assert violation.get("reason_code") == TOOL_TIMEOUT
    assert TOOL_TIMEOUT in result.get("emits", [])


def test_tool_stub_adapter_succeeds_no_block(repo_registry_and_root) -> None:
    """No adapter (stub): valid tool call completes without BLOCKED."""
    registry, policy_root = repo_registry_and_root
    initial_state = _minimal_initial_state(registry, policy_root=policy_root)
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 0,
        "agent_id": "A_OPS_0",
        "action_type": "TICK",
        "args": {"accession_id": "ACC001"},
        "tool_id": "read_lims_v1",
    }
    result = env.step(event)
    assert result.get("blocked_reason_code") not in (
        TOOL_EXEC_EXCEPTION,
        TOOL_TIMEOUT,
        TOOL_OUTPUT_MALFORMED,
    )


def test_execute_tool_safely_unit_exception() -> None:
    """execute_tool_safely returns (False, {}, tool_error) when adapter raises."""

    def raise_adapter(tool_id: str, args: dict):  # noqa: ARG001
        raise ValueError("unit test")

    ok, result, err = execute_tool_safely("read_lims_v1", {"accession_id": "A1"}, adapter=raise_adapter)
    assert ok is False
    assert result == {}
    assert err is not None
    assert err.get("reason_code") == TOOL_EXEC_EXCEPTION
    assert "unit test" in (err.get("message") or "")


def test_execute_tool_safely_unit_malformed() -> None:
    """execute_tool_safely returns TOOL_OUTPUT_MALFORMED when adapter returns non-dict."""

    def list_adapter(tool_id: str, args: dict):  # noqa: ARG001
        return [1, 2, 3]

    ok, result, err = execute_tool_safely("read_lims_v1", {"accession_id": "A1"}, adapter=list_adapter)
    assert ok is False
    assert err is not None
    assert err.get("reason_code") == TOOL_OUTPUT_MALFORMED


def test_execute_tool_safely_unit_timeout() -> None:
    """execute_tool_safely returns TOOL_TIMEOUT when adapter exceeds timeout."""

    def slow(tool_id: str, args: dict):  # noqa: ARG001
        time.sleep(5.0)
        return {}

    ok, result, err = execute_tool_safely("read_lims_v1", {}, adapter=slow, timeout_s=0.05)
    assert ok is False
    assert err is not None
    assert err.get("reason_code") == TOOL_TIMEOUT


def test_benchmark_runner_completes_without_uncaught_exceptions(
    tmp_path: Path,
) -> None:
    """Run a minimal benchmark path; no uncaught exceptions."""
    from labtrust_gym.benchmarks.runner import run_benchmark
    from labtrust_gym.benchmarks.tasks import get_task

    if get_task("throughput_sla") is None:
        pytest.skip("throughput_sla not available")
    try:
        results = run_benchmark(
            "throughput_sla",
            num_episodes=1,
            base_seed=0,
            out_path=tmp_path / "results.json",
            repo_root=Path(__file__).resolve().parents[1],
        )
    except Exception as e:
        pytest.fail(f"Benchmark runner raised: {e}")
    assert results is not None
