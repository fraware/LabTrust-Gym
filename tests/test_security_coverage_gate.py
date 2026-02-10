"""
Security coverage gate: every risk in risk_registry.v0.1.yaml must be covered by
security_coverage_map.v0.1.yaml (policy/security/) with either (a) at least one
covered_by entry (injection, attack_suite, or test), or (b) explicit
non_applicable with justification (notes). Referenced injections must exist in
injections.v0.2.yaml; referenced attack_suite refs must exist in
security_attack_suite.v0.1.yaml. CI fails on any new risk without coverage.
"""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.benchmarks.security_runner import load_attack_suite
from labtrust_gym.policy.loader import load_yaml
from labtrust_gym.policy.risks import load_risk_registry


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_security_coverage_map(repo_root: Path) -> dict[str, dict]:
    """Load security_coverage_map.v0.1.yaml; return risk_id -> entry."""
    path = repo_root / "policy" / "security" / "security_coverage_map.v0.1.yaml"
    if not path.exists():
        return {}
    data = load_yaml(path)
    if not isinstance(data, dict):
        return {}
    entries = data.get("entries")
    if not isinstance(entries, list):
        return {}
    out: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        risk_id = entry.get("risk_id")
        if risk_id and isinstance(risk_id, str):
            out[risk_id] = dict(entry)
    return out


def _valid_injection_ids(repo_root: Path) -> set[str]:
    """Load injections.v0.2.yaml; return set of injection_id."""
    path = repo_root / "policy" / "coordination" / "injections.v0.2.yaml"
    if not path.exists():
        return set()
    data = load_yaml(path)
    injections = (data or {}).get("injections") or []
    return {
        str(i["injection_id"])
        for i in injections
        if isinstance(i, dict) and i.get("injection_id")
    }


def _valid_attack_ids(repo_root: Path) -> set[str]:
    """Return set of attack_id from security_attack_suite.v0.1.yaml."""
    suite = load_attack_suite(repo_root)
    attacks = (suite or {}).get("attacks") or []
    return {
        str(a["attack_id"])
        for a in attacks
        if isinstance(a, dict) and a.get("attack_id")
    }


def test_security_coverage_map_exists_and_parses() -> None:
    """Security coverage map YAML exists and has entries list."""
    root = _repo_root()
    path = root / "policy" / "security" / "security_coverage_map.v0.1.yaml"
    assert path.exists(), f"Missing {path}"
    data = load_yaml(path)
    assert isinstance(data, dict), "security_coverage_map must be a YAML object"
    assert "version" in data
    entries = data.get("entries")
    assert isinstance(entries, list), "entries must be a list"
    assert len(entries) >= 1, "At least one entry required"


def test_every_risk_has_coverage_or_non_applicable() -> None:
    """Every risk has coverage map entry; each is covered or non_applicable+notes."""
    root = _repo_root()
    risk_reg = load_risk_registry(
        root / "policy" / "risks" / "risk_registry.v0.1.yaml"
    )
    coverage_map = _load_security_coverage_map(root)
    missing = set(risk_reg.risks) - set(coverage_map)
    assert not missing, (
        f"CI gate: risk_ids with no security coverage: {sorted(missing)}. "
        "Add to policy/security/security_coverage_map.v0.1.yaml."
    )
    invalid: list[str] = []
    for risk_id, entry in coverage_map.items():
        covered_by = entry.get("covered_by") or []
        non_applicable = entry.get("non_applicable") is True
        notes = (entry.get("notes") or "").strip()
        if non_applicable:
            if not notes:
                invalid.append(f"{risk_id} (non_applicable but notes empty)")
        else:
            if not covered_by:
                invalid.append(
                    f"{risk_id} (no covered_by and not non_applicable)"
                )
    assert not invalid, (
        "Entry must be non_applicable+notes or have covered_by. Invalid: "
        f"{invalid}"
    )


def test_coverage_injection_refs_exist_in_injections() -> None:
    """Every covered_by type=injection ref exists in injections.v0.2.yaml."""
    root = _repo_root()
    coverage_map = _load_security_coverage_map(root)
    valid_injections = _valid_injection_ids(root)
    bad: list[tuple[str, str]] = []
    for risk_id, entry in coverage_map.items():
        for item in entry.get("covered_by") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "injection":
                continue
            ref = item.get("ref")
            if ref and ref not in valid_injections:
                bad.append((risk_id, ref))
    assert not bad, (
        f"Injection refs not in injections.v0.2: {bad}. "
        "Add to injections.v0.2.yaml or remove from covered_by."
    )


def test_coverage_attack_suite_refs_exist() -> None:
    """Every covered_by type=attack_suite ref exists in security_attack_suite."""
    root = _repo_root()
    coverage_map = _load_security_coverage_map(root)
    valid_attacks = _valid_attack_ids(root)
    bad: list[tuple[str, str]] = []
    for risk_id, entry in coverage_map.items():
        for item in entry.get("covered_by") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "attack_suite":
                continue
            ref = item.get("ref")
            if ref and ref not in valid_attacks:
                bad.append((risk_id, ref))
    assert not bad, (
        f"attack_suite refs not in security_attack_suite: {bad}. "
        "Add to security_attack_suite.v0.1.yaml or remove from covered_by."
    )


def test_no_orphan_coverage_entries() -> None:
    """Every coverage map risk_id exists in risk_registry (no stale entries)."""
    root = _repo_root()
    risk_reg = load_risk_registry(
        root / "policy" / "risks" / "risk_registry.v0.1.yaml"
    )
    coverage_map = _load_security_coverage_map(root)
    orphan = set(coverage_map) - set(risk_reg.risks)
    assert not orphan, (
        f"Coverage map risk_ids not in risk_registry: {sorted(orphan)}. "
        "Remove from security_coverage_map or add to risk_registry."
    )


def test_coordination_pack_full_method_list_non_empty() -> None:
    """When --methods-from full is used, the pack method list is non-empty and excludes marl_ppo (and study-only placeholders)."""
    from labtrust_gym.studies.coordination_security_pack import _load_pack_config, _resolve_methods

    root = _repo_root()
    pack_config = _load_pack_config(root)
    methods = _resolve_methods(root, "full", pack_config)
    assert len(methods) >= 1, (
        "Coordination security pack --methods-from full must resolve to at least one method_id. "
        "Define method_ids.full in policy/coordination/coordination_security_pack.v0.1.yaml or ensure coordination_methods.v0.1.yaml exists."
    )
    assert "marl_ppo" not in methods, (
        "marl_ppo must be excluded from full method list (no checkpoint in repo)."
    )


def test_coordination_pack_full_method_list_used() -> None:
    """When pack config defines method_ids.full, --methods-from full uses that list (canonical list in one place)."""
    from labtrust_gym.studies.coordination_security_pack import _load_pack_config, _resolve_methods

    root = _repo_root()
    pack_config = _load_pack_config(root)
    full_list = (pack_config.get("method_ids") or {}).get("full")
    if not isinstance(full_list, list) or not full_list:
        return  # No canonical list in config; fallback to registry is acceptable
    methods = _resolve_methods(root, "full", pack_config)
    missing = set(full_list) - set(methods)
    extra = set(methods) - set(full_list)
    assert not missing, (
        f"method_ids.full in pack config has methods not returned by --methods-from full: {sorted(missing)}."
    )
    assert not extra, (
        f"--methods-from full returned methods not in method_ids.full: {sorted(extra)}. "
        "Canonical list should be used when defined."
    )
