"""
Risk registry: schema validation and loader.

- Valid risk_registry.v0.1.yaml validates against risk_registry.v0.1.schema.json.
- Invalid risk entry (e.g. bad category or missing required field) fails validation.
- load_risk_registry returns RiskRegistry; get_risk returns correct entry or None.
- Fingerprinting/loading is deterministic (no ambient randomness).
"""

from pathlib import Path

import pytest

from labtrust_gym.policy.loader import (
    PolicyLoadError,
    load_json,
    validate_against_schema,
)
from labtrust_gym.policy.risks import RiskRegistry, get_risk, load_risk_registry
from labtrust_gym.policy.validate import validate_policy_file_against_schema


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_risk_registry_validates_against_schema() -> None:
    """risk_registry.v0.1.yaml must validate against schema."""
    root = _repo_root()
    errors = validate_policy_file_against_schema(
        root,
        "policy/risks/risk_registry.v0.1.yaml",
        "risk_registry.v0.1.schema.json",
    )
    assert errors == [], f"Schema validation failed: {errors}"


def test_risk_registry_schema_rejects_invalid_category() -> None:
    """Invalid risk entry (bad category enum) must fail schema validation."""
    root = _repo_root()
    schema_path = root / "policy/schemas/risk_registry.v0.1.schema.json"
    if not schema_path.exists():
        pytest.skip("risk_registry.v0.1.schema.json not found")
    schema = load_json(schema_path)
    invalid = {
        "risk_registry": {
            "version": "0.1",
            "risks": [
                {
                    "risk_id": "R-TEST",
                    "name": "Test",
                    "category": "invalid_category",
                    "description": "Test risk.",
                }
            ],
        }
    }
    with pytest.raises(PolicyLoadError):
        validate_against_schema(invalid, schema, root / "risk_registry.v0.1.yaml")


def test_risk_registry_schema_rejects_missing_required() -> None:
    """Invalid risk entry (missing risk_id) must fail schema validation."""
    root = _repo_root()
    schema_path = root / "policy/schemas/risk_registry.v0.1.schema.json"
    if not schema_path.exists():
        pytest.skip("risk_registry.v0.1.schema.json not found")
    schema = load_json(schema_path)
    invalid = {
        "risk_registry": {
            "version": "0.1",
            "risks": [
                {
                    "name": "No risk_id",
                    "category": "tool",
                    "description": "Missing risk_id.",
                }
            ],
        }
    }
    with pytest.raises(PolicyLoadError):
        validate_against_schema(invalid, schema, root / "risk_registry.v0.1.yaml")


def test_load_risk_registry_returns_risk_registry() -> None:
    """load_risk_registry returns RiskRegistry with version and risks dict."""
    root = _repo_root()
    path = root / "policy/risks/risk_registry.v0.1.yaml"
    if not path.exists():
        pytest.skip("risk_registry.v0.1.yaml not found")
    registry = load_risk_registry(path)
    assert isinstance(registry, RiskRegistry)
    assert registry.version == "0.1"
    assert isinstance(registry.risks, dict)
    assert len(registry.risks) >= 1


def test_get_risk_returns_entry_or_none() -> None:
    """get_risk returns risk entry for known risk_id, None for unknown."""
    root = _repo_root()
    path = root / "policy/risks/risk_registry.v0.1.yaml"
    if not path.exists():
        pytest.skip("risk_registry.v0.1.yaml not found")
    registry = load_risk_registry(path)
    entry = get_risk(registry, "R-TOOL-001")
    assert entry is not None
    assert entry.get("risk_id") == "R-TOOL-001"
    assert entry.get("name") == "Tool Selection Errors"
    assert entry.get("category") == "tool"
    assert get_risk(registry, "R-NONEXISTENT") is None
    assert get_risk(registry, "") is None


def test_risk_registry_loading_deterministic() -> None:
    """Loading same file twice yields identical RiskRegistry.risks keys and content."""
    root = _repo_root()
    path = root / "policy/risks/risk_registry.v0.1.yaml"
    if not path.exists():
        pytest.skip("risk_registry.v0.1.yaml not found")
    r1 = load_risk_registry(path)
    r2 = load_risk_registry(path)
    assert r1.version == r2.version
    assert set(r1.risks.keys()) == set(r2.risks.keys())
    for k in r1.risks:
        assert r1.risks[k] == r2.risks[k]
