"""
Policy validation tests: fail if any required file is missing or invalid.

Uses labtrust_gym.policy.validate. All policy YAML/JSON are validated against
JSON schemas in policy/schemas/. Tests ensure valid policy passes and invalid
policy fails (missing required keys, wrong types).
"""

import tempfile
from pathlib import Path

import pytest

from labtrust_gym.policy.loader import PolicyLoadError, load_json, validate_against_schema
from labtrust_gym.policy.validate import (
    validate_all_policy_schemas,
    validate_emits_vocab,
    validate_golden_scenarios,
    validate_policy,
    validate_policy_file_against_schema,
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


def test_invalid_emits_vocab_missing_canonical_set_fails() -> None:
    """Invalid policy (missing required canonical_set) must fail schema validation."""
    root = _repo_root()
    schema_path = root / "policy" / "schemas" / "emits_vocab.v0.1.schema.json"
    assert schema_path.exists()
    schema = load_json(schema_path)
    invalid_data = {"emits_vocab": {"version": "0.1"}}
    with pytest.raises(PolicyLoadError) as exc_info:
        validate_against_schema(invalid_data, schema, Path("emits_vocab.v0.1.yaml"))
    assert "canonical_set" in str(exc_info.value).lower() or "schema" in str(exc_info.value).lower()


def test_invalid_golden_scenarios_missing_scenarios_fails() -> None:
    """Invalid golden (golden_suite without scenarios) must fail schema validation."""
    root = _repo_root()
    schema_path = root / "policy" / "schemas" / "golden_scenarios.v0.1.schema.json"
    assert schema_path.exists()
    schema = load_json(schema_path)
    invalid_data = {"golden_suite": {"version": "0.1"}}
    with pytest.raises(PolicyLoadError) as exc_info:
        validate_against_schema(invalid_data, schema, Path("golden_scenarios.v0.1.yaml"))
    assert "scenarios" in str(exc_info.value).lower() or "schema" in str(exc_info.value).lower()


def test_invalid_policy_file_against_schema_returns_errors() -> None:
    """validate_policy_file_against_schema returns errors when policy is invalid."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        policy_dir = root / "policy" / "emits"
        policy_dir.mkdir(parents=True)
        schema_dir = root / "policy" / "schemas"
        schema_dir.mkdir(parents=True)
        policy_path = policy_dir / "emits_vocab.v0.1.yaml"
        schema_path = schema_dir / "emits_vocab.v0.1.schema.json"
        policy_path.write_text('emits_vocab:\n  version: "0.1"\n', encoding="utf-8")
        schema_path.write_text(
            '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","required":["emits_vocab"],"properties":{"emits_vocab":{"type":"object","required":["canonical_set"],"properties":{"canonical_set":{"type":"array","minItems":1,"items":{"type":"string"}}}}}}',
            encoding="utf-8",
        )
        errors = validate_policy_file_against_schema(
            root, "policy/emits/emits_vocab.v0.1.yaml", "emits_vocab.v0.1.schema.json"
        )
        assert len(errors) > 0, "Expected validation errors for missing canonical_set"
        assert any("canonical_set" in e.lower() or "schema" in e.lower() for e in errors)


def test_validate_all_policy_schemas_includes_all_mapped_files() -> None:
    """validate_all_policy_schemas runs validation for every POLICY_FILES_WITH_SCHEMAS entry."""
    from labtrust_gym.policy.validate import POLICY_FILES_WITH_SCHEMAS

    root = _repo_root()
    errors = validate_all_policy_schemas(root)
    assert errors == [], f"All policy schema validations should pass: {errors}"
    assert len(POLICY_FILES_WITH_SCHEMAS) >= 8
