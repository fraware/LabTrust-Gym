"""
Phase 1 coordination matrix policy contract: YAML files validate against JSON schemas.

- Load each of coordination_matrix_inputs, coordination_matrix_column_map, coordination_matrix_spec.
- Validate against schema; assert strictness (no non-llm_live modes, valid direction, valid gate op).
- One negative test per file: mutate one field to invalid, assert validation raises.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from labtrust_gym.policy.loader import (
    PolicyLoadError,
    load_json,
    load_policy_file,
    validate_against_schema,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _validate(schema: dict, instance: dict, path: Path | None = None) -> None:
    validate_against_schema(instance, schema, path)


_POLICY_SCHEMA_PAIRS = [
    (
        "policy/coordination/coordination_matrix_inputs.v0.1.yaml",
        "policy/schemas/coordination_matrix_inputs.v0.1.schema.json",
    ),
    (
        "policy/coordination/coordination_matrix_column_map.v0.1.yaml",
        "policy/schemas/coordination_matrix_column_map.v0.1.schema.json",
    ),
    (
        "policy/coordination/coordination_matrix_spec.v0.1.yaml",
        "policy/schemas/coordination_matrix_spec.v0.1.schema.json",
    ),
]


def test_coordination_matrix_inputs_loads_and_validates() -> None:
    """coordination_matrix_inputs.v0.1.yaml loads and validates against its schema."""
    root = _repo_root()
    policy_path = root / "policy/coordination/coordination_matrix_inputs.v0.1.yaml"
    schema_path = root / "policy/schemas/coordination_matrix_inputs.v0.1.schema.json"
    if not policy_path.exists() or not schema_path.exists():
        pytest.skip("coordination_matrix_inputs or schema not found")
    data = load_policy_file(policy_path)
    schema = load_json(schema_path)
    _validate(schema, data, policy_path)


def test_coordination_matrix_column_map_loads_and_validates() -> None:
    """coordination_matrix_column_map.v0.1.yaml loads and validates against its schema."""
    root = _repo_root()
    policy_path = root / "policy/coordination/coordination_matrix_column_map.v0.1.yaml"
    schema_path = root / "policy/schemas/coordination_matrix_column_map.v0.1.schema.json"
    if not policy_path.exists() or not schema_path.exists():
        pytest.skip("coordination_matrix_column_map or schema not found")
    data = load_policy_file(policy_path)
    schema = load_json(schema_path)
    _validate(schema, data, policy_path)


def test_coordination_matrix_spec_loads_and_validates() -> None:
    """coordination_matrix_spec.v0.1.yaml loads and validates against its schema."""
    root = _repo_root()
    policy_path = root / "policy/coordination/coordination_matrix_spec.v0.1.yaml"
    schema_path = root / "policy/schemas/coordination_matrix_spec.v0.1.schema.json"
    if not policy_path.exists() or not schema_path.exists():
        pytest.skip("coordination_matrix_spec or schema not found")
    data = load_policy_file(policy_path)
    schema = load_json(schema_path)
    _validate(schema, data, policy_path)


def test_inputs_rejects_non_llm_live_pipeline_modes() -> None:
    """Validation must fail if pipeline_modes_allowed includes deterministic or llm_offline."""
    root = _repo_root()
    policy_path = root / "policy/coordination/coordination_matrix_inputs.v0.1.yaml"
    schema_path = root / "policy/schemas/coordination_matrix_inputs.v0.1.schema.json"
    if not policy_path.exists() or not schema_path.exists():
        pytest.skip("coordination_matrix_inputs or schema not found")
    data = load_policy_file(policy_path)
    schema = load_json(schema_path)

    for bad_mode in ("deterministic", "llm_offline"):
        bad = copy.deepcopy(data)
        bad["scope"] = copy.deepcopy(data["scope"])
        bad["scope"]["pipeline_modes_allowed"] = [bad_mode]
        with pytest.raises(PolicyLoadError):
            _validate(schema, bad, policy_path)


def test_inputs_rejects_invalid_metric_direction() -> None:
    """Validation must fail if a metric has an invalid direction."""
    root = _repo_root()
    policy_path = root / "policy/coordination/coordination_matrix_inputs.v0.1.yaml"
    schema_path = root / "policy/schemas/coordination_matrix_inputs.v0.1.schema.json"
    if not policy_path.exists() or not schema_path.exists():
        pytest.skip("coordination_matrix_inputs or schema not found")
    data = load_policy_file(policy_path)
    schema = load_json(schema_path)
    bad = copy.deepcopy(data)
    bad["clean_metrics"] = copy.deepcopy(data["clean_metrics"])
    bad["clean_metrics"][0] = copy.deepcopy(data["clean_metrics"][0])
    bad["clean_metrics"][0]["direction"] = "worse_is_better"
    with pytest.raises(PolicyLoadError):
        _validate(schema, bad, policy_path)


def test_inputs_rejects_invalid_gate_op() -> None:
    """Validation must fail if a gate uses an invalid op."""
    root = _repo_root()
    policy_path = root / "policy/coordination/coordination_matrix_inputs.v0.1.yaml"
    schema_path = root / "policy/schemas/coordination_matrix_inputs.v0.1.schema.json"
    if not policy_path.exists() or not schema_path.exists():
        pytest.skip("coordination_matrix_inputs or schema not found")
    data = load_policy_file(policy_path)
    schema = load_json(schema_path)
    bad = copy.deepcopy(data)
    bad["hard_gates"] = copy.deepcopy(data["hard_gates"])
    bad["hard_gates"][0] = copy.deepcopy(data["hard_gates"][0])
    bad["hard_gates"][0]["predicate"] = copy.deepcopy(bad["hard_gates"][0]["predicate"])
    bad["hard_gates"][0]["predicate"]["op"] = "~="
    with pytest.raises(PolicyLoadError):
        _validate(schema, bad, policy_path)


def test_inputs_negative_invalid_version() -> None:
    """Validation fails when version is not v0.1 (negative test)."""
    root = _repo_root()
    policy_path = root / "policy/coordination/coordination_matrix_inputs.v0.1.yaml"
    schema_path = root / "policy/schemas/coordination_matrix_inputs.v0.1.schema.json"
    if not policy_path.exists() or not schema_path.exists():
        pytest.skip("coordination_matrix_inputs or schema not found")
    data = load_policy_file(policy_path)
    schema = load_json(schema_path)
    bad = copy.deepcopy(data)
    bad["version"] = "v0.2"
    with pytest.raises(PolicyLoadError):
        _validate(schema, bad, policy_path)


def test_column_map_negative_invalid_transform() -> None:
    """Validation fails when transform is not in enum (negative test)."""
    root = _repo_root()
    policy_path = root / "policy/coordination/coordination_matrix_column_map.v0.1.yaml"
    schema_path = root / "policy/schemas/coordination_matrix_column_map.v0.1.schema.json"
    if not policy_path.exists() or not schema_path.exists():
        pytest.skip("coordination_matrix_column_map or schema not found")
    data = load_policy_file(policy_path)
    schema = load_json(schema_path)
    bad = copy.deepcopy(data)
    first_metric = next(iter(bad["column_map"].keys()))
    bad["column_map"] = copy.deepcopy(bad["column_map"])
    bad["column_map"][first_metric] = copy.deepcopy(bad["column_map"][first_metric])
    bad["column_map"][first_metric]["transform"] = "square_root"
    with pytest.raises(PolicyLoadError):
        _validate(schema, bad, policy_path)


def test_spec_negative_non_llm_live_scope() -> None:
    """Validation fails when scope.pipeline_modes_allowed is not exactly llm_live (negative test)."""
    root = _repo_root()
    policy_path = root / "policy/coordination/coordination_matrix_spec.v0.1.yaml"
    schema_path = root / "policy/schemas/coordination_matrix_spec.v0.1.schema.json"
    if not policy_path.exists() or not schema_path.exists():
        pytest.skip("coordination_matrix_spec or schema not found")
    data = load_policy_file(policy_path)
    schema = load_json(schema_path)
    bad = copy.deepcopy(data)
    bad["scope"] = copy.deepcopy(data["scope"])
    bad["scope"]["pipeline_modes_allowed"] = ["llm_live", "deterministic"]
    with pytest.raises(PolicyLoadError):
        _validate(schema, bad, policy_path)
