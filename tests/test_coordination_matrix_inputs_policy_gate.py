"""Policy gate: coordination_matrix_inputs.v0.1.yaml validates against its JSON schema."""

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


def test_coordination_matrix_inputs_policy_validates() -> None:
    """coordination_matrix_inputs.v0.1.yaml must validate against coordination_matrix_inputs.v0.1.schema.json."""
    root = _repo_root()
    policy_path = root / "policy" / "coordination" / "coordination_matrix_inputs.v0.1.yaml"
    schema_path = root / "policy" / "schemas" / "coordination_matrix_inputs.v0.1.schema.json"

    if not policy_path.exists() or not schema_path.exists():
        pytest.skip("coordination_matrix_inputs policy or schema not found")

    instance = _load_yaml(policy_path)
    schema = _load_json(schema_path)
    _validate(schema, instance)
