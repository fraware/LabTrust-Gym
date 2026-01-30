"""
Policy validation tests: fail if any required file is missing or invalid.

Uses labtrust_gym.policy.validate. Required files:
- policy/schemas/runner_output_contract.v0.1.schema.json (exists and valid JSON)
- policy/emits/emits_vocab.v0.1.yaml (canonical_set unique and non-empty)
- policy/golden/golden_scenarios.v0.1.yaml (parses, has golden_suite.scenarios)
"""

from pathlib import Path

import pytest

from labtrust_gym.policy.validate import (
    validate_emits_vocab,
    validate_golden_scenarios,
    validate_policy,
    validate_runner_output_contract_schema,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_validate_policy_returns_no_errors() -> None:
    """Full policy validation must pass; fails if any required file missing or invalid."""
    root = _repo_root()
    errors = validate_policy(root)
    assert errors == [], f"Policy validation failed: {errors}"


def test_runner_output_contract_schema_exists_and_parses() -> None:
    """Runner output contract schema file must exist and parse as valid JSON."""
    root = _repo_root()
    errors = validate_runner_output_contract_schema(root)
    assert errors == [], f"Runner output contract schema validation failed: {errors}"


def test_emits_vocab_canonical_set_unique_non_empty() -> None:
    """Emits vocab must have canonical_set that is unique and non-empty."""
    root = _repo_root()
    errors = validate_emits_vocab(root)
    assert errors == [], f"Emits vocab validation failed: {errors}"


def test_golden_scenarios_parses_and_has_required_fields() -> None:
    """Golden scenarios file must parse and have golden_suite.scenarios."""
    root = _repo_root()
    errors = validate_golden_scenarios(root)
    assert errors == [], f"Golden scenarios validation failed: {errors}"
