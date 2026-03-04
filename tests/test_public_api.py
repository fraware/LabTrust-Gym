"""
Public API regression tests.

Import and use only the documented public API. Ensures the contract we document
for the community is not broken by internal changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_validate_policy_returns_list() -> None:
    """validate_policy(root) returns a list of error strings."""
    from labtrust_gym.config import get_repo_root
    from labtrust_gym.policy.validate import validate_policy

    root = Path(get_repo_root())
    errors = validate_policy(root)
    assert isinstance(errors, list)
    assert all(isinstance(e, str) for e in errors)


def test_load_attack_suite_returns_dict_with_attacks() -> None:
    """load_attack_suite(policy_root) returns a dict with at least 'attacks'."""
    from labtrust_gym.benchmarks.security_runner import load_attack_suite
    from labtrust_gym.config import get_repo_root

    policy_root = Path(get_repo_root())
    suite = load_attack_suite(policy_root)
    assert isinstance(suite, dict)
    assert "attacks" in suite
    assert isinstance(suite["attacks"], list)


def test_get_repo_root_and_policy_path() -> None:
    """get_repo_root() and policy_path() are usable and consistent."""
    from labtrust_gym.config import get_repo_root, policy_path

    root = Path(get_repo_root())
    p = policy_path(root, "golden", "security_attack_suite.v0.1.yaml")
    assert p == root / "policy" / "golden" / "security_attack_suite.v0.1.yaml"


def test_get_repo_root_from_subdirectory() -> None:
    """get_repo_root() resolves repo when cwd is a subdirectory (e.g. tests/)."""
    import os

    from labtrust_gym.config import get_repo_root

    repo_root = Path(__file__).resolve().parent.parent
    if not (repo_root / "policy" / "emits").exists():
        pytest.skip("repo policy/emits not found (e.g. not run from repo)")
    orig_cwd = os.getcwd()
    try:
        os.chdir(repo_root / "tests")
        root = Path(get_repo_root())
        assert root == repo_root
        assert (root / "policy" / "emits").exists()
    finally:
        os.chdir(orig_cwd)


def test_action_contract_constants_importable() -> None:
    """Action contract constants are importable from envs.action_contract."""
    from labtrust_gym.envs.action_contract import (
        ACTION_NOOP,
        ACTION_START_RUN,
        VALID_ACTION_INDICES,
    )

    assert ACTION_NOOP == 0
    assert ACTION_START_RUN == 5
    assert len(VALID_ACTION_INDICES) == 6


def test_benchmark_env_protocol_importable() -> None:
    """BenchmarkEnv protocol is importable."""
    from labtrust_gym.benchmarks.env_protocol import BenchmarkEnv

    assert BenchmarkEnv is not None


def test_run_security_suite_returns_list_of_result_dicts() -> None:
    """run_security_suite returns a list of result dicts with attack_id and passed."""
    import tempfile

    import yaml

    from labtrust_gym.benchmarks.security_runner import run_security_suite

    with tempfile.TemporaryDirectory() as tmp:
        policy_root = Path(tmp)
        policy_golden = policy_root / "policy" / "golden"
        policy_golden.mkdir(parents=True)
        minimal_suite = {"version": "0.1", "controls": [], "attacks": []}
        (policy_golden / "security_attack_suite.v0.1.yaml").write_text(yaml.dump(minimal_suite), encoding="utf-8")
        results = run_security_suite(
            policy_root=policy_root,
            repo_root=policy_root,
            smoke_only=True,
            seed=42,
            skip_system_level=True,
        )
    assert isinstance(results, list)
    for r in results:
        assert isinstance(r, dict)
        assert "attack_id" in r
        assert "passed" in r
