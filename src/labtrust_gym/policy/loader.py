"""
Load and validate policy files from the policy directory.

Loads YAML and JSON from policy/ (and partner overlays). When a schema exists
in policy/schemas/, files are validated against it; otherwise structural checks
(required keys) are applied where needed. All load/validation errors include
the file path for clear reporting.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, TypeVar, cast

T = TypeVar("T")

# Optional: jsonschema is a dependency in pyproject.toml
from types import ModuleType

import yaml

from labtrust_gym.errors import PolicyLoadError

__all__ = [
    "PolicyLoadError",
    "load_json",
    "load_yaml",
    "load_yaml_optional",
    "load_policy_file",
    "validate_against_schema",
    "load_effective_policy",
    "get_partner_overlay_dir",
    "load_partners_index",
]

from labtrust_gym.policy.overlay import (
    merge_critical_thresholds,
    merge_enforcement_map,
    merge_equipment_registry,
    merge_escalation_ladder,
    merge_stability_policy,
)

try:
    import jsonschema as _jsonschema_module

    jsonschema: ModuleType | None = _jsonschema_module
except ImportError:
    jsonschema = None

# Process-level cache for load_effective_policy. Key: (root_resolved_str, partner_id).
# Invalid if policy files change on disk during the process. Disable with LABTRUST_POLICY_CACHE=0.
_EFFECTIVE_POLICY_CACHE: dict[tuple[str, str | None], tuple[dict[str, Any], str, str | None, str | None]] = {}


def _policy_cache_enabled() -> bool:
    return os.environ.get("LABTRUST_POLICY_CACHE", "1").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def load_json(path: Path) -> dict[str, Any]:
    """
    Load a JSON file. Raise PolicyLoadError with path on parse failure.
    """
    path = Path(path)
    if not path.exists():
        raise PolicyLoadError(path, "file not found")
    try:
        text = path.read_text(encoding="utf-8")
        return cast(dict[str, Any], json.loads(text))
    except json.JSONDecodeError as e:
        raise PolicyLoadError(path, f"invalid JSON: {e}") from e


def load_yaml(path: Path) -> dict[str, Any]:
    """
    Load a YAML file. Raise PolicyLoadError with path on parse failure.
    """
    path = Path(path)
    try:
        if not path.exists():
            raise PolicyLoadError(path, "file not found")
    except OSError as e:
        raise PolicyLoadError(path, f"file not found or inaccessible: {e}") from e
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


def load_yaml_optional(path: Path, default: T) -> T:
    """
    Load a YAML file if it exists; otherwise return default.
    Raises PolicyLoadError on parse/validation failure when the file exists.
    """
    path = Path(path)
    if not path.exists():
        return default
    try:
        return cast(T, load_yaml(path))
    except PolicyLoadError:
        raise
    except Exception as e:
        raise PolicyLoadError(path, str(e)) from e


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
    "security_attack_suite.v0.1.yaml": "security_attack_suite.v0.1.schema.json",
    "enforcement_map.v0.1.yaml": "enforcement_map.v0.1.schema.json",
    "escalation_ladder.v0.2.yaml": "escalation_ladder.v0.2.schema.json",
    "sites_policy.v0.1.yaml": "sites_policy.v0.1.schema.json",
    "key_registry.v0.1.yaml": "key_registry.v0.1.schema.json",
    "rbac_policy.v0.1.yaml": "rbac_policy.v0.1.schema.json",
    "prompt_registry.v0.1.yaml": "prompt_registry.v0.1.schema.json",
    "adversarial_detection.v0.1.yaml": "adversarial_detection.v0.1.schema.json",
    "agent_capabilities.v0.1.yaml": "agent_capabilities.v0.1.schema.json",
    "risk_registry.v0.1.yaml": "risk_registry.v0.1.schema.json",
    "coordination_methods.v0.1.yaml": "coordination_methods.v0.1.schema.json",
    "method_risk_matrix.v0.1.yaml": "method_risk_matrix.v0.1.schema.json",
    "coordination_study_spec.v0.1.yaml": "coordination_study_spec.v0.1.schema.json",
    "coordination_matrix_inputs.v0.1.yaml": "coordination_matrix_inputs.v0.1.schema.json",
    "coordination_matrix_column_map.v0.1.yaml": "coordination_matrix_column_map.v0.1.schema.json",
    "coordination_matrix_spec.v0.1.yaml": "coordination_matrix_spec.v0.1.schema.json",
    "tool_registry.v0.1.yaml": "tool_registry.v0.1.schema.json",
    "scripted_ops_policy.v0.1.yaml": "scripted_ops_policy.v0.1.schema.json",
    "scripted_runner_policy.v0.1.yaml": "scripted_runner_policy.v0.1.schema.json",
    "repair_policy.v0.1.yaml": "repair_policy.v0.1.schema.json",
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
CALIBRATION_FILENAME = "calibration.v0.1.yaml"
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
    return cast(
        dict[str, Any],
        data.get("equipment_registry", data) if isinstance(data, dict) else {},
    )


def _load_base_escalation_ladder(root: Path) -> dict[str, Any] | None:
    p = root / BASE_POLICY_PATHS["escalation_ladder"]
    if not p.exists():
        return None
    return cast(dict[str, Any] | None, load_yaml(p))


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
    return cast(
        dict[str, Any],
        data.get("equipment_registry", data) if isinstance(data, dict) else {},
    )


def _load_overlay_escalation_ladder(overlay_dir: Path) -> dict[str, Any] | None:
    p = overlay_dir / PARTNER_OVERLAY_FILES["escalation_ladder"]
    if not p.exists():
        return None
    return load_yaml(p)


def _load_overlay_calibration(overlay_dir: Path) -> dict[str, Any] | None:
    """Load partner calibration.v0.1.yaml if present. Validates against schema when available."""
    p = overlay_dir / CALIBRATION_FILENAME
    if not p.exists():
        return None
    data = load_yaml(p)
    if not isinstance(data, dict):
        return None
    schema_path = overlay_dir.parent.parent / "schemas" / "calibration.v0.1.schema.json"
    if schema_path.exists() and jsonschema is not None:
        try:
            schema = load_json(schema_path)
            validate_against_schema(data, schema, p)
        except PolicyLoadError:
            raise
    return data


def compute_calibration_fingerprint(calibration: dict[str, Any]) -> str:
    """Compute SHA-256 hash of canonical JSON of calibration (deterministic)."""
    payload = json.dumps(calibration, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compute_policy_fingerprint(effective_policy: dict[str, Any]) -> str:
    """Compute SHA-256 hash of canonical JSON of effective policy (deterministic)."""
    payload = json.dumps(effective_policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def get_effective_policy_file_paths(
    root: Path,
    partner_id: str | None = None,
) -> list[tuple[str, Path]]:
    """
    Return list of (relative_path, absolute_path) for all policy files that contribute
    to effective policy (after partner overlay). Paths relative to root. Deterministic order.
    """
    root = Path(root)
    out: list[tuple[str, Path]] = []
    for key, rel in BASE_POLICY_PATHS.items():
        p = root / rel
        if p.exists():
            out.append((rel, p))
    if partner_id:
        overlay_dir = get_partner_overlay_dir(root, partner_id)
        if overlay_dir.is_dir():
            for key, rel in PARTNER_OVERLAY_FILES.items():
                p = overlay_dir / rel
                if p.exists():
                    partner_rel = f"policy/partners/{partner_id}/{rel}"
                    out.append((partner_rel, p))
            cal_path = overlay_dir / CALIBRATION_FILENAME
            if cal_path.exists():
                out.append(
                    (
                        f"policy/partners/{partner_id}/{CALIBRATION_FILENAME}",
                        cal_path,
                    )
                )
    return sorted(out, key=lambda x: x[0])


def build_policy_pack_manifest(
    root: Path,
    partner_id: str | None = None,
) -> dict[str, Any]:
    """
    Build policy_pack_manifest.v0.1: list effective policy files with sha256, plus root_hash.
    root_hash = sha256(canonical_json({version, files})) excluding root_hash.
    """
    root = Path(root)
    paths = get_effective_policy_file_paths(root, partner_id)
    files: list[dict[str, Any]] = []
    for rel, abspath in paths:
        digest = hashlib.sha256(abspath.read_bytes()).hexdigest()
        files.append({"path": rel, "sha256": digest})
    manifest: dict[str, Any] = {
        "version": "0.1",
        "partner_id": partner_id,
        "files": files,
    }
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["root_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return manifest


def load_effective_policy(
    root: Path,
    partner_id: str | None = None,
) -> tuple[dict[str, Any], str, str | None, str | None]:
    """
    Load base policy; if partner_id given, load overlay and merge.
    Return (effective_policy, fingerprint, partner_id, calibration_fingerprint).

    effective_policy keys: critical_thresholds (list), stability_policy (dict), enforcement_map (dict),
    equipment_registry (dict). Used by engine when passed in initial_state["effective_policy"].

    Result is cached per (root, partner_id) when LABTRUST_POLICY_CACHE is enabled (default).
    Cache is process-scoped; do not rely on it if policy files change during the process.
    """
    root = Path(root)
    if _policy_cache_enabled():
        cache_key = (str(root.resolve()), partner_id)
        if cache_key in _EFFECTIVE_POLICY_CACHE:
            return _EFFECTIVE_POLICY_CACHE[cache_key]
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
        calibration = _load_overlay_calibration(overlay_dir)
    else:
        critical_list = base_critical
        stability_policy = base_stability
        enforcement_map = base_enforcement
        equipment_registry = base_equipment
        escalation_ladder = _load_base_escalation_ladder(root)
        calibration = None

    effective_policy = {
        "critical_thresholds": critical_list,
        "stability_policy": stability_policy,
        "enforcement_map": enforcement_map,
        "equipment_registry": equipment_registry,
        "escalation_ladder": escalation_ladder,
        "calibration": calibration,
    }
    fingerprint = compute_policy_fingerprint(effective_policy)
    calibration_fingerprint = compute_calibration_fingerprint(calibration) if calibration else None
    result = (effective_policy, fingerprint, partner_id, calibration_fingerprint)
    if _policy_cache_enabled():
        _EFFECTIVE_POLICY_CACHE[cache_key] = result
    return result


def load_policy_for_domain(
    root: Path,
    domain_id: str | None = None,
    partner_id: str | None = None,
) -> tuple[dict[str, Any], str, str | None, str | None, dict[str, Any]]:
    """
    Load base policy (via load_effective_policy); when domain_id is set and
    policy/domains/<domain_id>/ exists, load domain-specific YAML files from that
    path and return them as domain_overrides. Merge rules: domain_overrides extend
    or override base only for keys explicitly loaded from the domain dir.
    Returns (effective_policy, fingerprint, partner_id, calibration_fingerprint, domain_overrides).
    domain_overrides is empty when domain_id is None or the domain path does not exist.
    """
    effective_policy, fingerprint, pid, cal_fp = load_effective_policy(root, partner_id=partner_id)
    domain_overrides: dict[str, Any] = {}
    if domain_id:
        domain_dir = Path(root) / "policy" / "domains" / domain_id
        if domain_dir.is_dir():
            for path in sorted(domain_dir.glob("*.yaml")):
                try:
                    data = load_yaml(path)
                    if isinstance(data, dict):
                        key = path.stem
                        domain_overrides[key] = data
                except PolicyLoadError:
                    raise
                except Exception:
                    pass
            for path in sorted(domain_dir.glob("*.yml")):
                try:
                    data = load_yaml(path)
                    if isinstance(data, dict):
                        key = path.stem
                        domain_overrides[key] = data
                except PolicyLoadError:
                    raise
                except Exception:
                    pass
    return (effective_policy, fingerprint, pid, cal_fp, domain_overrides)
