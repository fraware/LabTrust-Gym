"""
Policy validation used by the CLI.

Validates:
- runner_output_contract schema file exists and parses (valid JSON).
- All policy YAML/JSON files against their JSON schemas in policy/schemas/.
- If partner_id given: overlay files (only those present) against same schemas;
  merged policy consistency (enforcement rules reference valid invariant_ids, etc.).

Policy file -> schema mapping is in loader.POLICY_FILE_SCHEMA_MAP.
All error messages include file paths. Does not change policy semantics; only validates.
"""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.policy.loader import (
    POLICY_FILE_SCHEMA_MAP,
    BASE_POLICY_PATHS,
    PolicyLoadError,
    load_effective_policy,
    load_json,
    load_policy_file,
    load_yaml,
    validate_against_schema,
    get_partner_overlay_dir,
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
    (
        "policy/invariants/invariant_registry.v1.0.yaml",
        "invariant_registry.v1.0.schema.json",
    ),
    (
        "policy/zones/zone_layout_policy.v0.1.yaml",
        "zone_layout_policy.v0.1.schema.json",
    ),
    (
        "policy/reason_codes/reason_code_registry.v0.1.yaml",
        "reason_code_registry.v0.1.schema.json",
    ),
    ("policy/tokens/token_registry.v0.1.yaml", "token_registry.v0.1.schema.json"),
    (
        "policy/tokens/dual_approval_policy.v0.1.yaml",
        "dual_approval_policy.v0.1.schema.json",
    ),
    (
        "policy/critical/critical_thresholds.v0.1.yaml",
        "critical_thresholds.v0.1.schema.json",
    ),
    (
        "policy/equipment/equipment_registry.v0.1.yaml",
        "equipment_registry.v0.1.schema.json",
    ),
    ("policy/golden/golden_scenarios.v0.1.yaml", "golden_scenarios.v0.1.schema.json"),
    (
        "policy/enforcement/enforcement_map.v0.1.yaml",
        "enforcement_map.v0.1.schema.json",
    ),
    ("policy/partners/partners_index.v0.1.yaml", "partners_index.v0.1.schema.json"),
    (
        "policy/critical/escalation_ladder.v0.2.yaml",
        "escalation_ladder.v0.2.schema.json",
    ),
    ("policy/sites/sites_policy.v0.1.yaml", "sites_policy.v0.1.schema.json"),
    ("policy/keys/key_registry.v0.1.yaml", "key_registry.v0.1.schema.json"),
    ("policy/rbac/rbac_policy.v0.1.yaml", "rbac_policy.v0.1.schema.json"),
    ("policy/llm/prompt_registry.v0.1.yaml", "prompt_registry.v0.1.schema.json"),
    (
        "policy/security/adversarial_detection.v0.1.yaml",
        "adversarial_detection.v0.1.schema.json",
    ),
    (
        "policy/security/agent_capabilities.v0.1.yaml",
        "agent_capabilities.v0.1.schema.json",
    ),
    ("policy/risks/risk_registry.v0.1.yaml", "risk_registry.v0.1.schema.json"),
    (
        "policy/coordination/coordination_methods.v0.1.yaml",
        "coordination_methods.v0.1.schema.json",
    ),
    (
        "policy/coordination/method_risk_matrix.v0.1.yaml",
        "method_risk_matrix.v0.1.schema.json",
    ),
    (
        "policy/coordination/coordination_study_spec.v0.1.yaml",
        "coordination_study_spec.v0.1.schema.json",
    ),
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
        errors.extend(
            validate_policy_file_against_schema(root, policy_rel_path, schema_name)
        )
    return errors


# Partner overlay: (rel path under partner dir, schema name). Stability has no schema in repo so not validated.
PARTNER_OVERLAY_VALIDATION: list[tuple[str, str]] = [
    ("critical/critical_thresholds.v0.1.yaml", "critical_thresholds.v0.1.schema.json"),
    ("enforcement/enforcement_map.v0.1.yaml", "enforcement_map.v0.1.schema.json"),
    ("equipment/equipment_registry.v0.1.yaml", "equipment_registry.v0.1.schema.json"),
    ("critical/escalation_ladder.v0.2.yaml", "escalation_ladder.v0.2.schema.json"),
    ("calibration.v0.1.yaml", "calibration.v0.1.schema.json"),
]


def validate_partner_overlay_files(root: Path, partner_id: str) -> list[str]:
    """Validate partner overlay files that exist, against same schemas as base. Returns error list."""
    errors: list[str] = []
    root = Path(root)
    overlay_dir = get_partner_overlay_dir(root, partner_id)
    if not overlay_dir.is_dir():
        errors.append(
            f"{overlay_dir}: partner overlay dir not found for {partner_id!r}"
        )
        return errors
    schemas_dir = root / "policy" / "schemas"
    for rel_file, schema_name in PARTNER_OVERLAY_VALIDATION:
        policy_path = overlay_dir / rel_file
        if not policy_path.exists():
            continue
        schema_path = schemas_dir / schema_name
        if not schema_path.exists():
            continue
        try:
            data = load_policy_file(policy_path)
        except PolicyLoadError as e:
            errors.append(str(e))
            continue
        try:
            schema = load_json(schema_path)
        except PolicyLoadError as e:
            errors.append(str(e))
            continue
        try:
            validate_against_schema(data, schema, policy_path)
        except PolicyLoadError as e:
            errors.append(str(e))
    return errors


def _invariant_ids_from_registry(root: Path) -> set[str]:
    """Load invariant registry and return set of invariant_id."""
    path = root / "policy" / "invariants" / "invariant_registry.v1.0.yaml"
    if not path.exists():
        return set()
    try:
        data = load_yaml(path)
    except PolicyLoadError:
        return set()
    invs = data.get("invariants") or data.get("registry") or []
    if not isinstance(invs, list):
        return set()
    return {str(i.get("invariant_id", "")) for i in invs if i.get("invariant_id")}


def validate_merged_policy_consistency(
    root: Path, partner_id: str | None = None
) -> list[str]:
    """
    Load effective policy (base + overlay if partner_id); check consistency.
    - Enforcement rules: match.invariant_id must be in invariant registry (if set).
    - Merge must succeed and fingerprint computed.
    """
    errors: list[str] = []
    root = Path(root)
    try:
        effective, fingerprint, _, _ = load_effective_policy(
            root, partner_id=partner_id
        )
    except PolicyLoadError as e:
        errors.append(str(e))
        return errors
    if not fingerprint:
        errors.append("merged policy fingerprint empty")
    inv_ids = _invariant_ids_from_registry(root)
    rules = (effective.get("enforcement_map") or {}).get("rules") or []
    for r in rules:
        match = r.get("match") or {}
        inv_id = match.get("invariant_id")
        if inv_id and inv_ids and inv_id not in inv_ids:
            errors.append(
                f"enforcement rule {r.get('rule_id', '?')}: invariant_id {inv_id!r} not in registry"
            )
    return errors


# LLM contract schema files (JSON schemas under policy/llm/) — validate parse and $schema
LLM_SCHEMA_FILES: list[str] = [
    "policy/llm/llm_action.schema.v0.2.json",
    "policy/llm/policy_summary.schema.v0.1.json",
    "policy/llm/policy_summary.schema.v0.2.json",
]


def validate_llm_schema_files(root: Path) -> list[str]:
    """Validate policy/llm/*.schema.*.json exist and parse as valid JSON with $schema."""
    errors: list[str] = []
    root = Path(root)
    for rel_path in LLM_SCHEMA_FILES:
        path = root / rel_path
        if not path.exists():
            errors.append(f"{path}: LLM schema file missing")
            continue
        try:
            data = load_json(path)
        except PolicyLoadError as e:
            errors.append(str(e))
            continue
        if not isinstance(data, dict):
            errors.append(f"{path}: expected JSON object")
            continue
        if "$schema" not in data:
            errors.append(f"{path}: missing $schema")
    return errors


def validate_policy(root: Path, partner_id: str | None = None) -> list[str]:
    """
    Run all policy validations. Returns list of error messages (with file paths);
    empty list means success. If partner_id is set, also validates overlay files and merged consistency.
    """
    errors: list[str] = []
    errors.extend(validate_runner_output_contract_schema(root))
    errors.extend(validate_all_policy_schemas(root))
    errors.extend(validate_llm_schema_files(root))
    if partner_id:
        errors.extend(validate_partner_overlay_files(root, partner_id))
        errors.extend(validate_merged_policy_consistency(root, partner_id))
    return errors
