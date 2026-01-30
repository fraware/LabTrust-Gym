"""
Policy validation used by the CLI.

Validates:
- runner_output_contract schema file exists and parses (valid JSON).
- emits_vocab.v0.1.yaml: canonical_set is unique and non-empty.
- golden_scenarios.v0.1.yaml: parses and has required fields (golden_suite, scenarios).

All error messages include file paths. Does not invent policy contents; assumes
policy files will be added later.
"""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.policy.loader import (
    PolicyLoadError,
    load_json,
    load_yaml,
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


def validate_emits_vocab(root: Path) -> list[str]:
    """
    Validate emits_vocab.v0.1.yaml: canonical_set exists, is non-empty, and unique.
    Returns list of error messages (with file path); empty if valid.
    """
    errors: list[str] = []
    root = Path(root)
    path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    if not path.exists():
        path = root / "emits_vocab.v0.1.yaml"
    if not path.exists():
        errors.append(f"{root / 'policy' / 'emits' / 'emits_vocab.v0.1.yaml'}: required file missing")
        return errors
    try:
        data = load_yaml(path)
    except PolicyLoadError as e:
        errors.append(str(e))
        return errors
    vocab = data.get("emits_vocab")
    if vocab is None:
        errors.append(f"{path}: missing top-level key 'emits_vocab'")
        return errors
    canonical = vocab.get("canonical_set")
    if canonical is None:
        errors.append(f"{path}: emits_vocab.canonical_set missing")
        return errors
    if not isinstance(canonical, list):
        errors.append(f"{path}: emits_vocab.canonical_set must be a list, got {type(canonical).__name__}")
        return errors
    if len(canonical) == 0:
        errors.append(f"{path}: emits_vocab.canonical_set must be non-empty")
        return errors
    seen = set()
    for i, item in enumerate(canonical):
        if not isinstance(item, str):
            errors.append(f"{path}: emits_vocab.canonical_set[{i}] must be string, got {type(item).__name__}")
        elif item in seen:
            errors.append(f"{path}: emits_vocab.canonical_set has duplicate entry {item!r}")
        else:
            seen.add(item)
    return errors


def validate_golden_scenarios(root: Path) -> list[str]:
    """
    Validate golden_scenarios.v0.1.yaml parses and has required fields: golden_suite, scenarios.
    Returns list of error messages (with file path); empty if valid.
    """
    errors: list[str] = []
    root = Path(root)
    path = root / "policy" / "golden" / "golden_scenarios.v0.1.yaml"
    if not path.exists():
        path = root / "golden_scenarios.v0.1.yaml"
    if not path.exists():
        errors.append(f"{root / 'policy' / 'golden' / 'golden_scenarios.v0.1.yaml'}: required file missing")
        return errors
    try:
        data = load_yaml(path)
    except PolicyLoadError as e:
        errors.append(str(e))
        return errors
    if "golden_suite" not in data:
        errors.append(f"{path}: missing top-level key 'golden_suite'")
        return errors
    suite = data["golden_suite"]
    if not isinstance(suite, dict):
        errors.append(f"{path}: golden_suite must be a mapping, got {type(suite).__name__}")
        return errors
    if "scenarios" not in suite:
        errors.append(f"{path}: golden_suite.scenarios missing")
        return errors
    scenarios = suite["scenarios"]
    if not isinstance(scenarios, list):
        errors.append(f"{path}: golden_suite.scenarios must be a list, got {type(scenarios).__name__}")
    return errors


def validate_policy(root: Path) -> list[str]:
    """
    Run all policy validations. Returns list of error messages (with file paths);
    empty list means success.
    """
    errors: list[str] = []
    errors.extend(validate_runner_output_contract_schema(root))
    errors.extend(validate_emits_vocab(root))
    errors.extend(validate_golden_scenarios(root))
    return errors
