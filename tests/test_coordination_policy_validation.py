"""
Coordination policy: method registry, method-risk matrix, study spec validation.

- coordination_methods.v0.1.yaml, method_risk_matrix.v0.1.yaml, coordination_study_spec.v0.1.yaml
  validate against their JSON schemas (via validate_policy / validate_policy_file_against_schema).
- Loaders return expected structure; required_bench cells and study spec fields are present.
- Loading is deterministic (no ambient randomness).
"""

from pathlib import Path

import pytest

from labtrust_gym.policy.loader import (
    PolicyLoadError,
    load_json,
    validate_against_schema,
)
from labtrust_gym.policy.validate import (
    POLICY_FILES_WITH_SCHEMAS,
    validate_policy,
    validate_policy_file_against_schema,
)
from labtrust_gym.policy.coordination import (
    get_required_bench_cells,
    load_coordination_methods,
    load_coordination_study_spec,
    load_method_risk_matrix,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_validate_policy_includes_coordination_files() -> None:
    """Full validate_policy passes and includes risk + coordination policy files."""
    root = _repo_root()
    errors = validate_policy(root)
    assert errors == [], f"Policy validation failed: {errors}"
    rel_paths = [p for p, _ in POLICY_FILES_WITH_SCHEMAS]
    assert any("risk_registry" in p for p in rel_paths)
    assert any("coordination_methods" in p for p in rel_paths)
    assert any("method_risk_matrix" in p for p in rel_paths)
    assert any("coordination_study_spec" in p for p in rel_paths)


def test_coordination_methods_validates_against_schema() -> None:
    """coordination_methods.v0.1.yaml must validate against schema."""
    root = _repo_root()
    errors = validate_policy_file_against_schema(
        root,
        "policy/coordination/coordination_methods.v0.1.yaml",
        "coordination_methods.v0.1.schema.json",
    )
    assert errors == [], f"Schema validation failed: {errors}"


def test_method_risk_matrix_validates_against_schema() -> None:
    """method_risk_matrix.v0.1.yaml must validate against schema."""
    root = _repo_root()
    errors = validate_policy_file_against_schema(
        root,
        "policy/coordination/method_risk_matrix.v0.1.yaml",
        "method_risk_matrix.v0.1.schema.json",
    )
    assert errors == [], f"Schema validation failed: {errors}"


def test_coordination_study_spec_validates_against_schema() -> None:
    """coordination_study_spec.v0.1.yaml must validate against schema."""
    root = _repo_root()
    errors = validate_policy_file_against_schema(
        root,
        "policy/coordination/coordination_study_spec.v0.1.yaml",
        "coordination_study_spec.v0.1.schema.json",
    )
    assert errors == [], f"Schema validation failed: {errors}"


def test_coordination_methods_schema_rejects_invalid_class() -> None:
    """Invalid method entry (bad coordination_class enum) must fail schema validation."""
    root = _repo_root()
    schema_path = root / "policy/schemas/coordination_methods.v0.1.schema.json"
    if not schema_path.exists():
        pytest.skip("coordination_methods.v0.1.schema.json not found")
    schema = load_json(schema_path)
    invalid = {
        "coordination_methods": {
            "version": "0.1",
            "methods": [
                {
                    "method_id": "test",
                    "name": "Test",
                    "coordination_class": "invalid_class",
                }
            ],
        }
    }
    with pytest.raises(PolicyLoadError):
        validate_against_schema(
            invalid, schema, root / "coordination_methods.v0.1.yaml"
        )


def test_method_risk_matrix_schema_rejects_invalid_coverage() -> None:
    """Invalid matrix cell (bad coverage enum) must fail schema validation."""
    root = _repo_root()
    schema_path = root / "policy/schemas/method_risk_matrix.v0.1.schema.json"
    if not schema_path.exists():
        pytest.skip("method_risk_matrix.v0.1.schema.json not found")
    schema = load_json(schema_path)
    invalid = {
        "method_risk_matrix": {
            "matrix_id": "test",
            "version": "0.1",
            "cells": [
                {
                    "method_id": "centralized_planner",
                    "risk_id": "R-TOOL-001",
                    "coverage": "invalid_coverage",
                }
            ],
        }
    }
    with pytest.raises(PolicyLoadError):
        validate_against_schema(invalid, schema, root / "method_risk_matrix.v0.1.yaml")


def test_load_coordination_methods_returns_dict() -> None:
    """load_coordination_methods returns method_id -> entry dict with expected methods."""
    root = _repo_root()
    path = root / "policy/coordination/coordination_methods.v0.1.yaml"
    if not path.exists():
        pytest.skip("coordination_methods.v0.1.yaml not found")
    methods = load_coordination_methods(path)
    assert isinstance(methods, dict)
    assert "centralized_planner" in methods
    assert "llm_constrained" in methods
    m = methods["centralized_planner"]
    assert m.get("method_id") == "centralized_planner"
    assert m.get("coordination_class") == "centralized"
    assert isinstance(m.get("known_weaknesses"), list)
    assert isinstance(m.get("required_controls"), list)


def test_load_method_risk_matrix_returns_cells() -> None:
    """load_method_risk_matrix returns matrix_id, version, and cells list."""
    root = _repo_root()
    path = root / "policy/coordination/method_risk_matrix.v0.1.yaml"
    if not path.exists():
        pytest.skip("method_risk_matrix.v0.1.yaml not found")
    matrix = load_method_risk_matrix(path)
    assert matrix.get("matrix_id")
    assert matrix.get("version") == "0.1"
    cells = matrix.get("cells")
    assert isinstance(cells, list)
    assert len(cells) >= 1
    cell = cells[0]
    assert "method_id" in cell and "risk_id" in cell and "coverage" in cell


def test_get_required_bench_cells_filters_correctly() -> None:
    """get_required_bench_cells returns only cells with required_bench true."""
    root = _repo_root()
    path = root / "policy/coordination/method_risk_matrix.v0.1.yaml"
    if not path.exists():
        pytest.skip("method_risk_matrix.v0.1.yaml not found")
    matrix = load_method_risk_matrix(path)
    required = get_required_bench_cells(matrix)
    assert isinstance(required, list)
    assert all(
        isinstance(c, dict) and c.get("required_bench") is True for c in required
    )
    assert len(required) <= len(matrix.get("cells", []))


def test_load_coordination_study_spec_returns_spec() -> None:
    """load_coordination_study_spec returns dict with study_id, seed_base, episodes_per_cell."""
    root = _repo_root()
    path = root / "policy/coordination/coordination_study_spec.v0.1.yaml"
    if not path.exists():
        pytest.skip("coordination_study_spec.v0.1.yaml not found")
    spec = load_coordination_study_spec(path)
    assert spec.get("study_id")
    assert "seed_base" in spec
    assert spec.get("episodes_per_cell") >= 1
    assert isinstance(spec.get("methods"), list)
    assert isinstance(spec.get("risks"), list)
    assert isinstance(spec.get("injections"), list)


def test_coordination_loading_deterministic() -> None:
    """Loading coordination files twice yields identical structures."""
    root = _repo_root()
    methods_path = root / "policy/coordination/coordination_methods.v0.1.yaml"
    matrix_path = root / "policy/coordination/method_risk_matrix.v0.1.yaml"
    spec_path = root / "policy/coordination/coordination_study_spec.v0.1.yaml"
    if not methods_path.exists() or not matrix_path.exists() or not spec_path.exists():
        pytest.skip("coordination policy files not found")
    m1 = load_coordination_methods(methods_path)
    m2 = load_coordination_methods(methods_path)
    assert m1 == m2
    mx1 = load_method_risk_matrix(matrix_path)
    mx2 = load_method_risk_matrix(matrix_path)
    assert mx1["matrix_id"] == mx2["matrix_id"]
    assert mx1["cells"] == mx2["cells"]
    s1 = load_coordination_study_spec(spec_path)
    s2 = load_coordination_study_spec(spec_path)
    assert s1 == s2
