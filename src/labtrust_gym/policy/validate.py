"""
Policy validation used by the CLI.

Validates:
- runner_output_contract schema file exists and parses (valid JSON).
- All policy YAML/JSON files against their JSON schemas in policy/schemas/.

Policy file -> schema mapping is in loader.POLICY_FILE_SCHEMA_MAP.
All error messages include file paths. Does not change policy semantics; only validates.
"""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.policy.loader import (
    PolicyLoadError,
    load_json,
    load_policy_file,
    validate_against_schema,
)


def validate_runner_output_contract_schema(root: Path) -> list[str]:
    """
    Validate that runner_output_contract.v0.1.schema.json exists and parses as valid JSON.
    Returns list of error messages (with file path); empty if valid.
    """
    errors: list[str] = []
    root = Path(root)
    schemas_dir = root / "policy" / "schemas"
    if not schemas_dir.is_dir():
        errors.append(f"{schemas_dir}: schemas directory not found")
        return errors
    path = schemas_dir / "runner_output_contract.v0.1.schema.json"
    if not path.exists():
        errors.append(f"{path}: required file missing")
        return errors
    try:
        load_json(path)
    except PolicyLoadError as e:
        errors.append(str(e))
    return errors


# Policy files to validate against schemas (path relative to root)
POLICY_FILES_WITH_SCHEMAS: list[tuple[str, str]] = [
    ("policy/emits/emits_vocab.v0.1.yaml", "emits_vocab.v0.1.schema.json"),
    ("policy/invariants/invariant_registry.v1.0.yaml", "invariant_registry.v1.0.schema.json"),
    ("policy/zones/zone_layout_policy.v0.1.yaml", "zone_layout_policy.v0.1.schema.json"),
    ("policy/reason_codes/reason_code_registry.v0.1.yaml", "reason_code_registry.v0.1.schema.json"),
    ("policy/tokens/token_registry.v0.1.yaml", "token_registry.v0.1.schema.json"),
    ("policy/tokens/dual_approval_policy.v0.1.yaml", "dual_approval_policy.v0.1.schema.json"),
    ("policy/critical/critical_thresholds.v0.1.yaml", "critical_thresholds.v0.1.schema.json"),
    ("policy/equipment/equipment_registry.v0.1.yaml", "equipment_registry.v0.1.schema.json"),
    ("policy/golden/golden_scenarios.v0.1.yaml", "golden_scenarios.v0.1.schema.json"),
    ("policy/enforcement/enforcement_map.v0.1.yaml", "enforcement_map.v0.1.schema.json"),
]


def validate_policy_file_against_schema(
    root: Path,
    policy_rel_path: str,
    schema_name: str,
) -> list[str]:
    """
    Load policy file (YAML/JSON), load schema, validate. Returns list of error messages.
    """
    errors: list[str] = []
    root = Path(root)
    policy_path = root / policy_rel_path
    schemas_dir = root / "policy" / "schemas"
    schema_path = schemas_dir / schema_name
    if not policy_path.exists():
        errors.append(f"{policy_path}: policy file missing")
        return errors
    if not schema_path.exists():
        errors.append(f"{schema_path}: schema file missing")
        return errors
    try:
        data = load_policy_file(policy_path)
    except PolicyLoadError as e:
        errors.append(str(e))
        return errors
    try:
        schema = load_json(schema_path)
    except PolicyLoadError as e:
        errors.append(str(e))
        return errors
    try:
        validate_against_schema(data, schema, policy_path)
    except PolicyLoadError as e:
        errors.append(str(e))
    return errors


def validate_emits_vocab(root: Path) -> list[str]:
    """Validate emits_vocab.v0.1.yaml against its JSON schema."""
    return validate_policy_file_against_schema(
        root,
        "policy/emits/emits_vocab.v0.1.yaml",
        "emits_vocab.v0.1.schema.json",
    )


def validate_golden_scenarios(root: Path) -> list[str]:
    """Validate golden_scenarios.v0.1.yaml against its JSON schema."""
    return validate_policy_file_against_schema(
        root,
        "policy/golden/golden_scenarios.v0.1.yaml",
        "golden_scenarios.v0.1.schema.json",
    )


def validate_all_policy_schemas(root: Path) -> list[str]:
    """Validate all policy files that have schemas. Returns list of error messages."""
    errors: list[str] = []
    for policy_rel_path, schema_name in POLICY_FILES_WITH_SCHEMAS:
        errors.extend(validate_policy_file_against_schema(root, policy_rel_path, schema_name))
    return errors


def validate_policy(root: Path) -> list[str]:
    """
    Run all policy validations. Returns list of error messages (with file paths);
    empty list means success.
    """
    errors: list[str] = []
    errors.extend(validate_runner_output_contract_schema(root))
    errors.extend(validate_all_policy_schemas(root))
    return errors
