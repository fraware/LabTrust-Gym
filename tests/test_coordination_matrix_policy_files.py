"""Policy-only check: coordination matrix policy YAML files in policy/coordination/ validate against policy/schemas/."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _validate(schema: dict, instance: dict) -> None:
    v = Draft202012Validator(schema)
    errors = sorted(v.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        msg = "\n".join([f"{list(e.path)}: {e.message}" for e in errors])
        raise AssertionError(f"Schema validation failed:\n{msg}")


_COORDINATION_MATRIX_POLICY_FILES = [
    ("coordination_matrix_inputs.v0.1.yaml", "coordination_matrix_inputs.v0.1.schema.json"),
    ("coordination_matrix_column_map.v0.1.yaml", "coordination_matrix_column_map.v0.1.schema.json"),
    ("coordination_matrix_spec.v0.1.yaml", "coordination_matrix_spec.v0.1.schema.json"),
]


def test_coordination_matrix_policy_files_exist() -> None:
    """All three coordination matrix policy files and their schemas must exist."""
    root = _repo_root()
    coord_dir = root / "policy" / "coordination"
    schemas_dir = root / "policy" / "schemas"
    for yaml_name, schema_name in _COORDINATION_MATRIX_POLICY_FILES:
        assert (coord_dir / yaml_name).exists(), f"Missing policy file: policy/coordination/{yaml_name}"
        assert (schemas_dir / schema_name).exists(), f"Missing schema: policy/schemas/{schema_name}"


@pytest.mark.parametrize("yaml_name, schema_name", _COORDINATION_MATRIX_POLICY_FILES)
def test_coordination_matrix_policy_file_validates_against_schema(yaml_name: str, schema_name: str) -> None:
    """Each coordination matrix policy YAML must validate against its JSON schema."""
    root = _repo_root()
    policy_path = root / "policy" / "coordination" / yaml_name
    schema_path = root / "policy" / "schemas" / schema_name

    if not policy_path.exists():
        pytest.skip(f"Policy file not found: {policy_path}")
    if not schema_path.exists():
        pytest.skip(f"Schema file not found: {schema_path}")

    instance = _load_yaml(policy_path)
    schema = _load_json(schema_path)
    _validate(schema, instance)
