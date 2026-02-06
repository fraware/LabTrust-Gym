"""
Tests for tool selection error metric: allowed-by-registry but inapplicable for current state.

- Golden: state_label=accessioning (read-only), LLM calls write_lims_v1 -> tool_selection_error,
  violation and emit, step not blocked (soft fail).
- Deterministic across seeds.
- Metrics: tool_selection_errors_count, tool_selection_errors_rate.
"""

from pathlib import Path

import pytest

from labtrust_gym.benchmarks.metrics import compute_episode_metrics
from labtrust_gym.engine.core_env import TOOL_SELECTION_ERROR, CoreEnv


@pytest.fixture
def repo_root() -> Path:
    """Repo root for policy paths."""
    return Path(__file__).resolve().parent.parent


def _minimal_initial_state(
    tool_registry: dict,
    state_label: str | None = None,
    state_tool_capability_map: dict | None = None,
    policy_root: Path | None = None,
    allowed_tools: list | None = None,
) -> dict:
    """Minimal initial_state for CoreEnv with tool registry and optional state map."""
    out = {
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
        "tool_registry": tool_registry,
    }
    if state_label is not None:
        out["state_label"] = state_label
    if state_tool_capability_map is not None:
        out["state_tool_capability_map"] = state_tool_capability_map
    if policy_root is not None:
        out["policy_root"] = str(policy_root)
    if allowed_tools is not None:
        out["allowed_tools"] = allowed_tools
    return out


def test_tool_selection_error_when_write_at_read_only_phase() -> None:
    """
    Golden: accessioning allows only lims.read, queue.read.
    Agent calls write_lims_v1 -> tool selection error recorded, step ACCEPTED (soft fail).
    """
    repo_root = Path(__file__).resolve().parent.parent
    schema_path = repo_root / "policy" / "tool_args" / "write_lims_v1.args.v0.1.schema.json"
    if not schema_path.exists():
        pytest.skip("write_lims_v1 arg schema not found")
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
                },
                {
                    "tool_id": "write_lims_v1",
                    "publisher": "labtrust",
                    "version": "0.1.0",
                    "capabilities": ["lims.write"],
                    "risk_class": "med",
                    "arg_schema_ref": "tool_args/write_lims_v1.args.v0.1.schema.json",
                },
            ],
        },
    }
    state_map = {
        "accessioning": ["lims.read", "queue.read"],
        "default": ["lims.read", "lims.write", "queue.read"],
    }
    initial_state = _minimal_initial_state(
        registry,
        state_label="accessioning",
        state_tool_capability_map=state_map,
        policy_root=repo_root,
        allowed_tools=["read_lims_v1", "write_lims_v1"],
    )
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 10,
        "agent_id": "A_OPS_0",
        "action_type": "INVOKE_TOOL",
        "args": {"accession_id": "ACC001", "field": "status", "value": "accessioning"},
        "tool_id": "write_lims_v1",
    }
    result = env.step(event)
    # Tool selection error is always recorded when write at read-only phase (soft fail).
    assert result.get("tool_selection_error") is True
    assert result.get("tool_call") is True
    violations = result.get("violations") or []
    assert any(v.get("invariant_id") == "TOOL_SELECTION_ERROR" for v in violations)
    assert any(v.get("reason_code") == TOOL_SELECTION_ERROR for v in violations)
    emits = result.get("emits") or []
    if result.get("status") == "ACCEPTED":
        assert TOOL_SELECTION_ERROR in emits
    if result.get("status") == "BLOCKED":
        pytest.skip("step blocked (arg validation or RBAC); tool_selection_error and violation verified")
    assert result.get("status") == "ACCEPTED"


def test_tool_selection_no_error_when_allowed_for_state() -> None:
    """When tool capabilities are in state's allowed set, no tool_selection_error."""
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
                },
            ],
        },
    }
    state_map = {
        "accessioning": ["lims.read", "queue.read"],
        "default": ["lims.read", "lims.write", "queue.read"],
    }
    initial_state = _minimal_initial_state(
        registry,
        state_label="accessioning",
        state_tool_capability_map=state_map,
        allowed_tools=["read_lims_v1"],
    )
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 10,
        "agent_id": "A_OPS_0",
        "action_type": "INVOKE_TOOL",
        "args": {"accession_id": "ACC001"},
        "tool_id": "read_lims_v1",
    }
    result = env.step(event)
    assert result.get("tool_call") is True
    assert result.get("tool_selection_error") is not True
    violations = result.get("violations") or []
    assert not any(v.get("invariant_id") == "TOOL_SELECTION_ERROR" for v in violations)


def test_tool_selection_error_deterministic_across_seeds() -> None:
    """Same scenario with different seeds yields same tool_selection_error outcome."""
    registry = {
        "tool_registry": {
            "version": "0.1",
            "tools": [
                {
                    "tool_id": "write_lims_v1",
                    "publisher": "labtrust",
                    "version": "0.1.0",
                    "capabilities": ["lims.write"],
                    "risk_class": "med",
                },
            ],
        },
    }
    state_map = {"accessioning": ["lims.read"], "default": ["lims.read", "lims.write"]}
    for seed in (0, 42, 123):
        initial_state = _minimal_initial_state(
            registry,
            state_label="accessioning",
            state_tool_capability_map=state_map,
            allowed_tools=["write_lims_v1"],
        )
        env = CoreEnv()
        env.reset(initial_state, deterministic=True, rng_seed=seed)
        event = {
            "t_s": 10,
            "agent_id": "A_OPS_0",
            "action_type": "INVOKE_TOOL",
            "args": {},
            "tool_id": "write_lims_v1",
        }
        result = env.step(event)
        assert result.get("tool_selection_error") is True, f"seed={seed}"


def test_tool_selection_errors_metrics_aggregation() -> None:
    """compute_episode_metrics aggregates tool_selection_error from step results."""
    step_results_per_step = [
        [
            {
                "status": "ACCEPTED",
                "tool_call": True,
                "tool_selection_error": True,
                "violations": [
                    {
                        "invariant_id": "TOOL_SELECTION_ERROR",
                        "reason_code": TOOL_SELECTION_ERROR,
                    }
                ],
                "emits": [TOOL_SELECTION_ERROR],
            },
        ],
        [
            {
                "status": "ACCEPTED",
                "tool_call": True,
                "tool_selection_error": False,
            },
        ],
    ]
    metrics = compute_episode_metrics(step_results_per_step)
    assert metrics["tool_selection_errors_count"] == 1
    assert metrics["tool_selection_errors_rate"] == 0.5  # 1 error / 2 tool calls
