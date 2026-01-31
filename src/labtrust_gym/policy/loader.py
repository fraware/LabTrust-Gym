"""
Policy loader: load YAML/JSON from policy/ and validate against schemas.

- JSON files: validated against JSON Schema in policy/schemas/ when a schema exists.
- YAML files: loaded with safe_load; optionally converted to JSON and validated
  against a schema, or structurally validated (required keys) where schemas
  do not exist yet.

All errors include the file path for clear reporting.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

# Optional: jsonschema is a dependency in pyproject.toml
try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]


class PolicyLoadError(Exception):
    """Raised when a policy file cannot be loaded or validated. Message includes path."""

    def __init__(self, path: Path | str, message: str) -> None:
        self.path = Path(path) if isinstance(path, str) else path
        super().__init__(f"{self.path}: {message}")


def load_json(path: Path) -> dict[str, Any]:
    """
    Load a JSON file. Raise PolicyLoadError with path on parse failure.
    """
    path = Path(path)
    if not path.exists():
        raise PolicyLoadError(path, "file not found")
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise PolicyLoadError(path, f"invalid JSON: {e}") from e


def load_yaml(path: Path) -> dict[str, Any]:
    """
    Load a YAML file. Raise PolicyLoadError with path on parse failure.
    """
    path = Path(path)
    if not path.exists():
        raise PolicyLoadError(path, "file not found")
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise PolicyLoadError(path, f"invalid YAML: {e}") from e
    if data is None:
        raise PolicyLoadError(path, "empty or null document")
    if not isinstance(data, dict):
        raise PolicyLoadError(path, f"expected mapping, got {type(data).__name__}")
    return data


def load_policy_file(path: Path) -> dict[str, Any]:
    """
    Load a policy file (YAML or JSON) by suffix. Raise PolicyLoadError with path on failure.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_json(path)
    if suffix in (".yaml", ".yml"):
        return load_yaml(path)
    raise PolicyLoadError(path, f"unsupported extension {suffix!r}; use .json, .yaml, or .yml")


def validate_against_schema(
    data: dict[str, Any],
    schema: dict[str, Any],
    path: Path | None = None,
) -> None:
    """
    Validate data against a JSON Schema. Raise PolicyLoadError (with path if given) on failure.

    Uses jsonschema Draft 2020-12 when available; otherwise raises if validation is requested
    and jsonschema is not installed.
    """
    if jsonschema is None:
        raise PolicyLoadError(
            path or Path("."),
            "jsonschema is required for schema validation; install with pip install jsonschema",
        )
    try:
        jsonschema.validate(instance=data, schema=schema)
    except PolicyLoadError:
        raise
    except jsonschema.ValidationError as e:
        msg = f"schema validation failed: {e}"
        if getattr(e, "absolute_path", None):
            msg += f" at {e.absolute_path}"
        raise PolicyLoadError(path or Path("."), msg) from e
    except Exception as e:
        raise PolicyLoadError(path or Path("."), f"schema validation failed: {e}") from e


# Policy file -> schema file mapping (filename under policy/ -> schema under policy/schemas/)
POLICY_FILE_SCHEMA_MAP: dict[str, str] = {
    "test_catalogue.seed.v0.1.json": "test_catalogue.schema.v0.1.json",
    "emits_vocab.v0.1.yaml": "emits_vocab.v0.1.schema.json",
    "invariant_registry.v1.0.yaml": "invariant_registry.v1.0.schema.json",
    "zone_layout_policy.v0.1.yaml": "zone_layout_policy.v0.1.schema.json",
    "reason_code_registry.v0.1.yaml": "reason_code_registry.v0.1.schema.json",
    "token_registry.v0.1.yaml": "token_registry.v0.1.schema.json",
    "dual_approval_policy.v0.1.yaml": "dual_approval_policy.v0.1.schema.json",
    "critical_thresholds.v0.1.yaml": "critical_thresholds.v0.1.schema.json",
    "equipment_registry.v0.1.yaml": "equipment_registry.v0.1.schema.json",
    "golden_scenarios.v0.1.yaml": "golden_scenarios.v0.1.schema.json",
    "enforcement_map.v0.1.yaml": "enforcement_map.v0.1.schema.json",
}


def get_schema_path_for_file(file_path: Path, schemas_dir: Path) -> Path | None:
    """
    Return the schema path for a given policy file if we have a known mapping; else None.

    Uses POLICY_FILE_SCHEMA_MAP. Any .json in schemas/ is a schema itself (no validation).
    """
    file_path = Path(file_path).resolve()
    schemas_dir = Path(schemas_dir).resolve()
    name = file_path.name
    schema_name = POLICY_FILE_SCHEMA_MAP.get(name)
    if schema_name:
        return schemas_dir / schema_name
    return None
