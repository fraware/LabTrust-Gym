"""
Tests for tool argument validation: typed and range-checked tool calls.

- Invalid/missing required args -> BLOCKED with TOOL_ARG_SCHEMA_FAIL.
- Out-of-range values -> BLOCKED with TOOL_ARG_RANGE_FAIL.
- Valid args -> pass gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.tools.arg_validation import (
    TOOL_ARG_RANGE_FAIL,
    TOOL_ARG_SCHEMA_FAIL,
    load_arg_schema,
    validate_tool_args,
)
from labtrust_gym.tools.registry import get_tool_entry, load_tool_registry


def _minimal_initial_state(registry: dict, policy_root: Path | None = None) -> dict:
    """Minimal initial_state so CoreEnv reset and step (tool + arg gate) run."""
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
    return state


@pytest.fixture
def repo_registry_and_root():
    """Load real tool registry and repo root (policy/tool_args/ must exist)."""
    from labtrust_gym.config import get_repo_root

    root = Path(get_repo_root())
    registry = load_tool_registry(root)
    if not registry.get("tool_registry", {}).get("tools"):
        pytest.skip("policy/tool_registry.v0.1.yaml has no tools")
    return registry, root


def test_invalid_missing_required_args_blocked_with_schema_fail(
    repo_registry_and_root,
) -> None:
    """Missing required args (e.g. accession_id for read_lims_v1) -> TOOL_ARG_SCHEMA_FAIL."""
    registry, policy_root = repo_registry_and_root
    initial_state = _minimal_initial_state(registry, policy_root)
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 0,
        "agent_id": "A_OPS_0",
        "action_type": "TICK",
        "args": {},
        "tool_id": "read_lims_v1",
    }
    result = env.step(event)
    assert result.get("status") == "BLOCKED"
    assert result.get("blocked_reason_code") == TOOL_ARG_SCHEMA_FAIL


def test_wrong_type_args_blocked_with_schema_fail(repo_registry_and_root) -> None:
    """Wrong type (e.g. accession_id as number) -> TOOL_ARG_SCHEMA_FAIL."""
    registry, policy_root = repo_registry_and_root
    initial_state = _minimal_initial_state(registry, policy_root)
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 0,
        "agent_id": "A_OPS_0",
        "action_type": "TICK",
        "args": {"accession_id": 12345},
        "tool_id": "read_lims_v1",
    }
    result = env.step(event)
    assert result.get("status") == "BLOCKED"
    assert result.get("blocked_reason_code") == TOOL_ARG_SCHEMA_FAIL


def test_out_of_range_blocked_with_range_fail(repo_registry_and_root) -> None:
    """Args within schema but out of range (e.g. limit > max) -> TOOL_ARG_RANGE_FAIL."""
    registry, policy_root = repo_registry_and_root
    initial_state = _minimal_initial_state(registry, policy_root)
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 0,
        "agent_id": "A_OPS_0",
        "action_type": "TICK",
        "args": {"accession_id": "ACC001", "limit": 2000},
        "tool_id": "read_lims_v1",
    }
    result = env.step(event)
    assert result.get("status") == "BLOCKED"
    assert result.get("blocked_reason_code") == TOOL_ARG_RANGE_FAIL


def test_valid_args_pass_gate(repo_registry_and_root) -> None:
    """Valid args -> no TOOL_ARG_* block."""
    registry, policy_root = repo_registry_and_root
    initial_state = _minimal_initial_state(registry, policy_root)
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
    assert result.get("blocked_reason_code") != TOOL_ARG_SCHEMA_FAIL
    assert result.get("blocked_reason_code") != TOOL_ARG_RANGE_FAIL


def test_valid_args_with_optional_limit_pass(repo_registry_and_root) -> None:
    """Valid args including in-range optional limit -> pass."""
    registry, policy_root = repo_registry_and_root
    initial_state = _minimal_initial_state(registry, policy_root)
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 0,
        "agent_id": "A_OPS_0",
        "action_type": "TICK",
        "args": {"accession_id": "ACC001", "limit": 100},
        "tool_id": "read_lims_v1",
    }
    result = env.step(event)
    assert result.get("blocked_reason_code") != TOOL_ARG_SCHEMA_FAIL
    assert result.get("blocked_reason_code") != TOOL_ARG_RANGE_FAIL


def test_load_arg_schema(repo_registry_and_root) -> None:
    """load_arg_schema(ref, policy_root) returns the schema dict."""
    _registry, policy_root = repo_registry_and_root
    schema = load_arg_schema(
        "tool_args/read_lims_v1.args.v0.1.schema.json", policy_root
    )
    assert isinstance(schema, dict)
    assert schema.get("type") == "object"
    assert "accession_id" in schema.get("required", [])
    assert "properties" in schema


def test_validate_tool_args_unit(repo_registry_and_root) -> None:
    """validate_tool_args returns (ok, reason_code, details) as specified."""
    registry, policy_root = repo_registry_and_root
    entry = get_tool_entry(registry, "read_lims_v1")
    assert entry is not None and entry.get("arg_schema_ref")

    ok, reason, details = validate_tool_args(
        "read_lims_v1", {"accession_id": "A1"}, registry, policy_root
    )
    assert ok is True
    assert reason is None

    ok2, reason2, _ = validate_tool_args("read_lims_v1", {}, registry, policy_root)
    assert ok2 is False
    assert reason2 == TOOL_ARG_SCHEMA_FAIL

    ok3, reason3, _ = validate_tool_args(
        "read_lims_v1", {"accession_id": "A1", "limit": 9999}, registry, policy_root
    )
    assert ok3 is False
    assert reason3 == TOOL_ARG_RANGE_FAIL
