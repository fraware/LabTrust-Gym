"""Test catalogue schema and seed. Validates catalogue JSON against schema."""

import json
from pathlib import Path

import jsonschema
import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_catalogue_seed_valid_against_schema() -> None:
    root = _repo_root()
    schema_path = root / "policy" / "schemas" / "test_catalogue.schema.v0.1.json"
    seed_path = root / "policy" / "catalogue" / "test_catalogue.seed.v0.1.json"
    if not seed_path.exists():
        seed_path = root / "test_catalogue.seed.v0.1.json"
    if not schema_path.exists() or not seed_path.exists():
        pytest.skip("Catalogue schema or seed not found")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    jsonschema.validate(instance=data, schema=schema)
