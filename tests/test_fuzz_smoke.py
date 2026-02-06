"""
Smoke tests for the fuzz harness: deterministic generation and one short session.

Verifies that event sequences are deterministic given seed and that
run_fuzz_session runs without error (contract and determinism checks).
"""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.testing.fuzz import (
    generate_event_sequence,
    run_fuzz_session,
)
from labtrust_gym.tools.registry import load_tool_registry


def _repo_root() -> Path:
    from labtrust_gym.config import get_repo_root

    return Path(get_repo_root())


def _minimal_initial_state():
    root = _repo_root()
    registry = load_tool_registry(root) or {}
    return {
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
        "policy_root": root,
    }


def test_generate_event_sequence_deterministic() -> None:
    """Same seed produces the same event sequence."""
    root = _repo_root()
    a = generate_event_sequence(42, policy_root=root, max_steps=10)
    b = generate_event_sequence(42, policy_root=root, max_steps=10)
    assert a == b
    assert len(a) <= 10


def test_fuzz_session_smoke() -> None:
    """One short fuzz session runs and passes contract/determinism checks."""
    root = _repo_root()
    passed, failures = run_fuzz_session(
        seed=100,
        initial_state_factory=_minimal_initial_state,
        env_factory=lambda: CoreEnv(),
        policy_root=root,
        max_steps=8,
        max_sequences=2,
        check_determinism=True,
        out_dir=Path("runs/fuzz_failures"),
    )
    assert passed, failures
    assert len(failures) == 0
