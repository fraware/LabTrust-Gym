"""
Repair policy resolution: _load_repair_policy, _resolve_repair_caps, and integration with LLMCentralPlanner.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from labtrust_gym.baselines.coordination.registry import (
    _load_repair_policy,
    _resolve_repair_caps,
    make_coordination_method,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_resolve_repair_caps_scale_config_only() -> None:
    """With no repair_policy, scale_config wins (backward compat)."""
    max_repairs, blocked_threshold = _resolve_repair_caps(
        "llm_central_planner", {}, {"max_repairs": 1, "blocked_threshold": 0}
    )
    assert max_repairs == 1
    assert blocked_threshold == 0

    max_repairs, blocked_threshold = _resolve_repair_caps(
        "llm_central_planner", {}, {"max_repairs": 5, "blocked_threshold": 2}
    )
    assert max_repairs == 5
    assert blocked_threshold == 2


def test_resolve_repair_caps_policy_overrides_scale_config() -> None:
    """Repair policy top-level overrides scale_config."""
    repair_policy = {"max_repairs": 2, "blocked_threshold": 1}
    scale_config = {"max_repairs": 1, "blocked_threshold": 0}
    max_repairs, blocked_threshold = _resolve_repair_caps("llm_central_planner", repair_policy, scale_config)
    assert max_repairs == 2
    assert blocked_threshold == 1


def test_resolve_repair_caps_per_method_override() -> None:
    """per_method[method_id] overrides repair policy top-level."""
    repair_policy = {
        "max_repairs": 1,
        "blocked_threshold": 0,
        "per_method": {
            "llm_central_planner": {"max_repairs": 3, "blocked_threshold": 1},
        },
    }
    scale_config = {"max_repairs": 5, "blocked_threshold": 2}
    max_repairs, blocked_threshold = _resolve_repair_caps("llm_central_planner", repair_policy, scale_config)
    assert max_repairs == 3
    assert blocked_threshold == 1


def test_resolve_repair_caps_per_method_other_method_gets_top_level() -> None:
    """Another method without per_method entry gets repair policy top-level, not scale_config."""
    repair_policy = {
        "max_repairs": 1,
        "blocked_threshold": 0,
        "per_method": {
            "llm_central_planner": {"max_repairs": 3},
        },
    }
    scale_config = {"max_repairs": 5, "blocked_threshold": 2}
    max_repairs, blocked_threshold = _resolve_repair_caps("other_method", repair_policy, scale_config)
    assert max_repairs == 1
    assert blocked_threshold == 0


def test_load_repair_policy_missing_returns_empty() -> None:
    """When repair_policy file is missing, _load_repair_policy returns empty dict."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        policy = _load_repair_policy(root)
    assert policy == {}


def test_load_repair_policy_none_root_returns_empty() -> None:
    """When repo_root is None, _load_repair_policy returns empty dict."""
    assert _load_repair_policy(None) == {}


def test_llm_central_planner_gets_caps_from_repair_policy() -> None:
    """make_coordination_method with repo_root and repair_policy file uses policy values."""
    root = _repo_root()
    policy = {}
    scale_config = {"max_repairs": 99, "blocked_threshold": 99}
    method = make_coordination_method(
        "llm_central_planner",
        policy,
        repo_root=root,
        scale_config=scale_config,
    )
    assert hasattr(method, "_max_repairs") and hasattr(method, "_blocked_threshold")
    assert method._max_repairs == 1
    assert method._blocked_threshold == 0


def test_llm_central_planner_repair_policy_file_overrides_scale_config() -> None:
    """With repair_policy.v0.1.yaml present, its values override scale_config."""
    root = _repo_root()
    repair_path = root / "policy" / "coordination" / "repair_policy.v0.1.yaml"
    if not repair_path.exists():
        pytest.skip("repair_policy.v0.1.yaml not in repo")
    policy = {}
    scale_config = {"max_repairs": 10, "blocked_threshold": 5}
    method = make_coordination_method(
        "llm_central_planner",
        policy,
        repo_root=root,
        scale_config=scale_config,
    )
    assert method._max_repairs == 1
    assert method._blocked_threshold == 0


def test_llm_central_planner_no_repair_file_scale_config_wins() -> None:
    """When repo_root has no repair_policy file, scale_config is used (backward compat)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "policy" / "coordination").mkdir(parents=True)
        policy = {}
        scale_config = {"max_repairs": 4, "blocked_threshold": 2}
        method = make_coordination_method(
            "llm_central_planner",
            policy,
            repo_root=root,
            scale_config=scale_config,
        )
        assert method._max_repairs == 4
        assert method._blocked_threshold == 2
