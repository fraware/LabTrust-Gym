"""
Risk coverage regression: every coordination-relevant risk in
risk_registry.v0.1.yaml must map to (a) coordination injection in
injections.v0.2.yaml, (b) security attack suite case in
security_attack_suite.v0.1.yaml, or (c) explicit not_applicable with
justification. Fails CI when coverage regresses.
"""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.benchmarks.security_runner import load_attack_suite
from labtrust_gym.policy.loader import load_yaml
from labtrust_gym.policy.risks import (
    load_risk_coverage_registry,
    load_risk_registry,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _valid_injection_ids(repo_root: Path) -> set[str]:
    """Load policy/coordination/injections.v0.2.yaml; return set of injection_id."""
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
    """Return set of attack_id from security_attack_suite."""
    suite = load_attack_suite(repo_root)
    attacks = (suite or {}).get("attacks") or []
    return {
        str(a["attack_id"])
        for a in attacks
        if isinstance(a, dict) and a.get("attack_id")
    }


def test_risk_coverage_registry_exists_and_parses() -> None:
    """Coverage registry YAML exists and has risk_coverage_registry.coverage list."""
    root = _repo_root()
    path = root / "policy" / "risks" / "risk_coverage_registry.v0.1.yaml"
    assert path.exists(), f"Missing {path}"
    reg = load_risk_coverage_registry(path)
    assert reg.version == "0.1"
    assert isinstance(reg.coverage, dict)
    assert len(reg.coverage) >= 1


def test_every_risk_has_coverage_entry() -> None:
    """Every risk in risk_registry has an entry in risk_coverage_registry."""
    root = _repo_root()
    risk_reg = load_risk_registry(
        root / "policy" / "risks" / "risk_registry.v0.1.yaml"
    )
    cov_reg = load_risk_coverage_registry(
        root / "policy" / "risks" / "risk_coverage_registry.v0.1.yaml"
    )
    missing = set(risk_reg.risks) - set(cov_reg.coverage)
    msg = (
        f"Coverage regression: risk_ids with no coverage: {sorted(missing)}. "
        "Add each to risk_coverage_registry with injection_ids, attack_ids, "
        "or not_applicable_justification."
    )
    assert not missing, msg


def test_every_coverage_entry_has_valid_type() -> None:
    """Each entry has injection_ids, attack_ids, or not_applicable_justification."""
    root = _repo_root()
    cov_reg = load_risk_coverage_registry(
        root / "policy" / "risks" / "risk_coverage_registry.v0.1.yaml"
    )
    invalid: list[str] = []
    for risk_id, entry in cov_reg.coverage.items():
        inj = entry.get("injection_ids") or []
        att = entry.get("attack_ids") or []
        na = (entry.get("not_applicable_justification") or "").strip()
        if not inj and not att and not na:
            invalid.append(risk_id)
    msg = (
        "Coverage entry must have at least one of injection_ids, attack_ids, "
        f"not_applicable_justification: {invalid}"
    )
    assert not invalid, msg


def test_coverage_injection_ids_exist_in_injections() -> None:
    """Every injection_id in coverage exists in injections.v0.2.yaml."""
    root = _repo_root()
    cov_reg = load_risk_coverage_registry(
        root / "policy" / "risks" / "risk_coverage_registry.v0.1.yaml"
    )
    valid = _valid_injection_ids(root)
    bad: list[tuple[str, str]] = []
    for risk_id, entry in cov_reg.coverage.items():
        for iid in entry.get("injection_ids") or []:
            if iid not in valid:
                bad.append((risk_id, iid))
    msg = (
        f"Coverage references injection_ids not in injections.v0.2: {bad}. "
        "Add to policy/coordination/injections.v0.2.yaml or remove from coverage."
    )
    assert not bad, msg


def test_coverage_attack_ids_exist_in_security_attack_suite() -> None:
    """Every attack_id in coverage exists in security_attack_suite.v0.1.yaml."""
    root = _repo_root()
    cov_reg = load_risk_coverage_registry(
        root / "policy" / "risks" / "risk_coverage_registry.v0.1.yaml"
    )
    valid = _valid_attack_ids(root)
    bad: list[tuple[str, str]] = []
    for risk_id, entry in cov_reg.coverage.items():
        for aid in entry.get("attack_ids") or []:
            if aid not in valid:
                bad.append((risk_id, aid))
    msg = (
        f"Coverage references attack_ids not in security_attack_suite: {bad}. "
        "Add to policy/golden/security_attack_suite.v0.1.yaml or remove."
    )
    assert not bad, msg


def test_no_orphan_coverage_entries() -> None:
    """Every coverage entry risk_id exists in risk_registry (no stale entries)."""
    root = _repo_root()
    risk_reg = load_risk_registry(
        root / "policy" / "risks" / "risk_registry.v0.1.yaml"
    )
    cov_reg = load_risk_coverage_registry(
        root / "policy" / "risks" / "risk_coverage_registry.v0.1.yaml"
    )
    orphan = set(cov_reg.coverage) - set(risk_reg.risks)
    msg = (
        f"Coverage has risk_ids not in risk_registry (stale): {sorted(orphan)}. "
        "Remove from risk_coverage_registry or add to risk_registry."
    )
    assert not orphan, msg
