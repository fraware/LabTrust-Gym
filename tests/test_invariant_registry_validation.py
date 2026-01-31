"""
Invariant registry: schema validation and loader.
"""

from pathlib import Path

import pytest

from labtrust_gym.policy.loader import load_json, validate_against_schema
from labtrust_gym.policy.validate import validate_policy_file_against_schema
from labtrust_gym.policy.invariants_registry import load_invariant_registry
from labtrust_gym.policy.loader import PolicyLoadError


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_invariant_registry_validates_against_schema() -> None:
    """invariant_registry.v1.0.yaml must validate against schema."""
    root = _repo_root()
    errors = validate_policy_file_against_schema(
        root,
        "policy/invariants/invariant_registry.v1.0.yaml",
        "invariant_registry.v1.0.schema.json",
    )
    assert errors == [], f"Schema validation failed: {errors}"


def test_invariant_registry_load_returns_entries() -> None:
    """load_invariant_registry returns list of InvariantEntry with expected fields."""
    root = _repo_root()
    path = root / "policy/invariants/invariant_registry.v1.0.yaml"
    if not path.exists():
        pytest.skip("invariant_registry.v1.0.yaml not found")
    entries = load_invariant_registry(path)
    assert len(entries) >= 1
    e = entries[0]
    assert e.invariant_id
    assert e.title
    assert e.severity in ("info", "low", "med", "high", "critical")
    assert e.scope in ("specimen", "result", "device", "zone", "agent", "system")
    assert "type" in e.logic_template
    assert e.logic_template["type"] in ("transition", "state", "temporal")


def test_invariant_registry_schema_rejects_invalid() -> None:
    """Invalid data (wrong severity) must fail schema validation."""
    root = _repo_root()
    schema_path = root / "policy/schemas/invariant_registry.v1.0.schema.json"
    if not schema_path.exists():
        pytest.skip("schema not found")
    schema = load_json(schema_path)
    invalid = {
        "registry_version": "1.0",
        "invariants": [
            {
                "invariant_id": "INV-TEST",
                "title": "Test",
                "severity": "invalid_severity",
                "scope": "system",
                "logic_template": {"type": "state", "parameters": {}},
            }
        ],
    }
    with pytest.raises((PolicyLoadError, Exception)):
        validate_against_schema(invalid, schema, root / "test.yaml")
