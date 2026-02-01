"""
Policy loader: load YAML/JSON from policy/ and validate against schemas.

- JSON files: validated against JSON Schema in policy/schemas/ when a schema exists.
- YAML files: loaded with safe_load; optionally converted to JSON and validated
  against a schema, or structurally validated (required keys) where schemas
  do not exist yet.

All errors include the file path for clear reporting.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Tuple

import yaml

from labtrust_gym.policy.overlay import (
    merge_critical_thresholds,
    merge_enforcement_map,
    merge_equipment_registry,
    merge_escalation_ladder,
    merge_stability_policy,
)

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
    "escalation_ladder.v0.2.yaml": "escalation_ladder.v0.2.schema.json",
    "sites_policy.v0.1.yaml": "sites_policy.v0.1.schema.json",
    "key_registry.v0.1.yaml": "key_registry.v0.1.schema.json",
    "rbac_policy.v0.1.yaml": "rbac_policy.v0.1.schema.json",
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


# --- Partner overlay resolution ---

PARTNERS_INDEX_FILENAME = "partners_index.v0.1.yaml"
PARTNER_OVERLAY_FILES = {
    "critical_thresholds": "critical/critical_thresholds.v0.1.yaml",
    "stability_policy": "stability/stability_policy.v0.1.yaml",
    "enforcement_map": "enforcement/enforcement_map.v0.1.yaml",
    "equipment_registry": "equipment/equipment_registry.v0.1.yaml",
    "escalation_ladder": "critical/escalation_ladder.v0.2.yaml",
}
BASE_POLICY_PATHS = {
    "critical_thresholds": "policy/critical/critical_thresholds.v0.1.yaml",
    "stability_policy": "policy/stability/stability_policy.v0.1.yaml",
    "enforcement_map": "policy/enforcement/enforcement_map.v0.1.yaml",
    "equipment_registry": "policy/equipment/equipment_registry.v0.1.yaml",
    "escalation_ladder": "policy/critical/escalation_ladder.v0.2.yaml",
}


def load_partners_index(root: Path) -> list[dict[str, Any]]:
    """Load partners index YAML. Returns list of partner entries (partner_id, description, overlay_path)."""
    root = Path(root)
    path = root / "policy" / "partners" / PARTNERS_INDEX_FILENAME
    if not path.exists():
        return []
    data = load_yaml(path)
    partners = data.get("partners")
    if not isinstance(partners, list):
        return []
    return [p for p in partners if isinstance(p, dict) and p.get("partner_id")]


def get_partner_overlay_dir(root: Path, partner_id: str) -> Path:
    """Return policy/partners/<partner_id>/ directory path."""
    return Path(root) / "policy" / "partners" / partner_id


def _load_base_critical_list(root: Path) -> list[dict[str, Any]]:
    p = root / BASE_POLICY_PATHS["critical_thresholds"]
    if not p.exists():
        return []
    data = load_yaml(p)
    ct = data.get("critical_thresholds") or {}
    entries = ct.get("defaults_rcpath2017") or ct.get("thresholds") or []
    return list(entries) if isinstance(entries, list) else []


def _load_base_stability(root: Path) -> dict[str, Any]:
    p = root / BASE_POLICY_PATHS["stability_policy"]
    if not p.exists():
        return {}
    return load_yaml(p)


def _load_base_enforcement(root: Path) -> dict[str, Any]:
    p = root / BASE_POLICY_PATHS["enforcement_map"]
    if not p.exists():
        return {"version": "0.1", "rules": []}
    data = load_yaml(p)
    rules = data.get("rules")
    if not isinstance(rules, list):
        rules = []
    return {"version": data.get("version", "0.1"), "rules": rules}


def _load_base_equipment(root: Path) -> dict[str, Any]:
    p = root / BASE_POLICY_PATHS["equipment_registry"]
    if not p.exists():
        return {"device_types": {}, "device_instances": []}
    data = load_yaml(p)
    return data.get("equipment_registry", data) if isinstance(data, dict) else {}


def _load_base_escalation_ladder(root: Path) -> dict[str, Any] | None:
    p = root / BASE_POLICY_PATHS["escalation_ladder"]
    if not p.exists():
        return None
    return load_yaml(p)


def _load_overlay_critical_list(overlay_dir: Path) -> list[dict[str, Any]] | None:
    p = overlay_dir / PARTNER_OVERLAY_FILES["critical_thresholds"]
    if not p.exists():
        return None
    data = load_yaml(p)
    ct = data.get("critical_thresholds") or {}
    entries = ct.get("defaults_rcpath2017") or ct.get("thresholds") or []
    return list(entries) if isinstance(entries, list) else []


def _load_overlay_stability(overlay_dir: Path) -> dict[str, Any] | None:
    p = overlay_dir / PARTNER_OVERLAY_FILES["stability_policy"]
    if not p.exists():
        return None
    return load_yaml(p)


def _load_overlay_enforcement(overlay_dir: Path) -> dict[str, Any] | None:
    p = overlay_dir / PARTNER_OVERLAY_FILES["enforcement_map"]
    if not p.exists():
        return None
    data = load_yaml(p)
    rules = data.get("rules")
    if not isinstance(rules, list):
        rules = []
    return {"version": data.get("version", "0.1"), "rules": rules}


def _load_overlay_equipment(overlay_dir: Path) -> dict[str, Any] | None:
    p = overlay_dir / PARTNER_OVERLAY_FILES["equipment_registry"]
    if not p.exists():
        return None
    data = load_yaml(p)
    return data.get("equipment_registry", data) if isinstance(data, dict) else {}


def _load_overlay_escalation_ladder(overlay_dir: Path) -> dict[str, Any] | None:
    p = overlay_dir / PARTNER_OVERLAY_FILES["escalation_ladder"]
    if not p.exists():
        return None
    return load_yaml(p)


def compute_policy_fingerprint(effective_policy: dict[str, Any]) -> str:
    """Compute SHA-256 hash of canonical JSON of effective policy (deterministic)."""
    payload = json.dumps(effective_policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_effective_policy(
    root: Path,
    partner_id: str | None = None,
) -> Tuple[dict[str, Any], str, str | None]:
    """
    Load base policy; if partner_id given, load overlay and merge. Return (effective_policy, fingerprint, partner_id).

    effective_policy keys: critical_thresholds (list), stability_policy (dict), enforcement_map (dict),
    equipment_registry (dict). Used by engine when passed in initial_state["effective_policy"].
    """
    root = Path(root)
    base_critical = _load_base_critical_list(root)
    base_stability = _load_base_stability(root)
    base_enforcement = _load_base_enforcement(root)
    base_equipment = _load_base_equipment(root)

    if partner_id:
        overlay_dir = get_partner_overlay_dir(root, partner_id)
        if not overlay_dir.is_dir():
            raise PolicyLoadError(overlay_dir, f"partner overlay dir not found for {partner_id!r}")
        overlay_critical = _load_overlay_critical_list(overlay_dir)
        overlay_stability = _load_overlay_stability(overlay_dir)
        overlay_enforcement = _load_overlay_enforcement(overlay_dir)
        overlay_equipment = _load_overlay_equipment(overlay_dir)

        critical_list = (
            merge_critical_thresholds(base_critical, overlay_critical)
            if overlay_critical is not None
            else base_critical
        )
        stability_policy = (
            merge_stability_policy(base_stability, overlay_stability)
            if overlay_stability is not None
            else base_stability
        )
        enforcement_map = (
            merge_enforcement_map(base_enforcement, overlay_enforcement)
            if overlay_enforcement is not None
            else base_enforcement
        )
        equipment_registry = (
            merge_equipment_registry(base_equipment, overlay_equipment)
            if overlay_equipment is not None
            else base_equipment
        )
        base_ladder = _load_base_escalation_ladder(root)
        overlay_ladder = _load_overlay_escalation_ladder(overlay_dir)
        escalation_ladder = (
            merge_escalation_ladder(base_ladder or {}, overlay_ladder or {})
            if overlay_ladder is not None and base_ladder is not None
            else (overlay_ladder if overlay_ladder is not None else base_ladder)
        )
        if escalation_ladder is None:
            escalation_ladder = base_ladder
    else:
        critical_list = base_critical
        stability_policy = base_stability
        enforcement_map = base_enforcement
        equipment_registry = base_equipment
        escalation_ladder = _load_base_escalation_ladder(root)

    effective_policy = {
        "critical_thresholds": critical_list,
        "stability_policy": stability_policy,
        "enforcement_map": enforcement_map,
        "equipment_registry": equipment_registry,
        "escalation_ladder": escalation_ladder,
    }
    fingerprint = compute_policy_fingerprint(effective_policy)
    return effective_policy, fingerprint, partner_id
