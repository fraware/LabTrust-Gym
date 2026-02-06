"""
Securitization packet: coverage (risk -> control -> tests -> artifacts),
reason_codes.md from registry, deps_inventory.json (SBOM-like).

Deterministic: same policy inputs yield same outputs. Used in package-release
to produce SECURITY/coverage.md, coverage.json, reason_codes.md,
deps_inventory.json.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from labtrust_gym.benchmarks.security_runner import load_attack_suite
from labtrust_gym.policy.reason_codes import load_reason_code_registry
from labtrust_gym.policy.risks import load_risk_registry


def _build_coverage_data(
    policy_root: Path,
) -> dict[str, Any]:
    """
    Build risk -> control -> tests -> artifacts mapping from risk_registry
    and security_attack_suite. Deterministic for same policy files.
    """
    suite = load_attack_suite(policy_root)
    attacks = suite.get("attacks") or []
    controls = {c["control_id"]: c for c in (suite.get("controls") or [])}
    risk_reg_path = policy_root / "policy" / "risks" / "risk_registry.v0.1.yaml"
    try:
        risk_reg = load_risk_registry(risk_reg_path)
    except Exception:
        risk_reg = None
    risk_entries: dict[str, list[dict[str, Any]]] = {}
    for a in attacks:
        risk_id = a.get("risk_id") or "unknown"
        entry = {
            "attack_id": a.get("attack_id"),
            "control_id": a.get("control_id"),
            "scenario_ref": a.get("scenario_ref"),
            "test_ref": a.get("test_ref"),
            "expected_outcome": a.get("expected_outcome"),
            "smoke": a.get("smoke"),
        }
        risk_entries.setdefault(risk_id, []).append(entry)
    coverage: dict[str, Any] = {
        "version": "0.1",
        "risk_to_controls": {},
        "control_to_tests": {},
        "artifacts": ["SECURITY/attack_results.json", "receipts/"],
    }
    control_to_tests: dict[str, list[str]] = {}
    for risk_id, entries in risk_entries.items():
        control_ids = list({e["control_id"] for e in entries if e["control_id"]})
        coverage["risk_to_controls"][risk_id] = {
            "controls": control_ids,
            "attacks": [e["attack_id"] for e in entries],
        }
        for e in entries:
            cid = e["control_id"]
            if cid:
                key = e.get("scenario_ref") or e.get("test_ref") or e["attack_id"]
                control_to_tests.setdefault(cid, []).append(key)
    coverage["control_to_tests"] = control_to_tests
    risk_names: dict[str, str] = {}
    if risk_reg:
        for rid, r in risk_reg.risks.items():
            risk_names[rid] = r.get("name", rid)
    coverage["risk_names"] = risk_names
    coverage["control_names"] = {cid: c.get("name", cid) for cid, c in controls.items()}
    return coverage


def write_coverage(
    policy_root: Path,
    out_dir: Path,
) -> dict[str, Any]:
    """Write SECURITY/coverage.json and SECURITY/coverage.md. Returns coverage dict."""
    coverage = _build_coverage_data(policy_root)
    security_dir = out_dir / "SECURITY"
    security_dir.mkdir(parents=True, exist_ok=True)
    (security_dir / "coverage.json").write_text(
        json.dumps(coverage, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    lines = [
        "# Security coverage",
        "",
        "Risk -> control -> tests -> artifacts mapping (from security_attack_suite).",
        "",
        "## Risk to controls",
        "",
    ]
    for risk_id, data in sorted(coverage.get("risk_to_controls", {}).items()):
        name = coverage.get("risk_names", {}).get(risk_id, risk_id)
        lines.append(f"- **{risk_id}** ({name})")
        lines.append(f"  - Controls: {', '.join(data.get('controls', []))}")
        lines.append(f"  - Attacks: {', '.join(data.get('attacks', []))}")
        lines.append("")
    lines.append("## Control to tests")
    for cid, tests in sorted(coverage.get("control_to_tests", {}).items()):
        name = coverage.get("control_names", {}).get(cid, cid)
        lines.append(f"- **{cid}** ({name}): {', '.join(tests)}")
    lines.append("")
    lines.append("## Artifacts")
    for art in coverage.get("artifacts", []):
        lines.append(f"- {art}")
    (security_dir / "coverage.md").write_text("\n".join(lines), encoding="utf-8")
    return coverage


def write_reason_codes_md(
    policy_root: Path,
    out_dir: Path,
    namespaces: list[str] | None = None,
) -> None:
    """
    Generate SECURITY/reason_codes.md from reason_code_registry.
    If namespaces is set (e.g. TOOL, COORD, MEM), only those are included.
    """
    path = policy_root / "policy" / "reason_codes" / "reason_code_registry.v0.1.yaml"
    if not path.exists():
        return
    registry = load_reason_code_registry(path)
    security_dir = out_dir / "SECURITY"
    security_dir.mkdir(parents=True, exist_ok=True)
    codes = list(registry.items())
    if namespaces:
        codes = [(k, v) for k, v in codes if v.get("namespace") in namespaces]
    codes.sort(key=lambda x: (x[1].get("namespace", ""), x[0]))
    lines = [
        "# Reason codes (from reason_code_registry)",
        "",
        "TOOL/COORD/MEM and related security-relevant codes.",
        "",
        "| Code | Namespace | Severity | Description |",
        "|------|-----------|----------|--------------|",
    ]
    for code, info in codes:
        ns = info.get("namespace", "")
        sev = info.get("severity", "")
        desc = (info.get("description") or "")[:60]
        lines.append(f"| {code} | {ns} | {sev} | {desc} |")
    (security_dir / "reason_codes.md").write_text("\n".join(lines), encoding="utf-8")


def write_deps_inventory(
    policy_root: Path,
    out_dir: Path,
) -> None:
    """
    Write SECURITY/deps_inventory.json: minimal SBOM-like with tool_registry
    fingerprint and policy file links (RBAC, coordination, memory).
    """
    security_dir = out_dir / "SECURITY"
    security_dir.mkdir(parents=True, exist_ok=True)
    inv: dict[str, Any] = {
        "version": "0.1",
        "tool_registry": None,
        "rbac_policy_path": "policy/rbac/rbac_policy.v0.1.yaml",
        "policy_paths": [],
    }
    try:
        from labtrust_gym.tools.registry import (
            load_tool_registry,
            tool_registry_fingerprint,
        )

        reg = load_tool_registry(policy_root)
        if reg:
            inv["tool_registry"] = {
                "path": "policy/tool_registry.v0.1.yaml",
                "fingerprint": tool_registry_fingerprint(reg),
            }
    except Exception:
        pass
    try:
        from labtrust_gym.auth.authorize import rbac_policy_fingerprint
        from labtrust_gym.engine.rbac import load_rbac_policy

        rbac_path = policy_root / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
        if rbac_path.exists():
            rbac = load_rbac_policy(rbac_path)
            inv["rbac_policy_fingerprint"] = rbac_policy_fingerprint(rbac)
    except Exception:
        pass
    for rel in [
        "policy/risks/risk_registry.v0.1.yaml",
        "policy/golden/security_attack_suite.v0.1.yaml",
        "policy/reason_codes/reason_code_registry.v0.1.yaml",
    ]:
        p = policy_root / rel
        if p.exists():
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            inv["policy_paths"].append({"path": rel, "sha256": h})
    (security_dir / "deps_inventory.json").write_text(
        json.dumps(inv, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def emit_securitization_packet(
    policy_root: Path,
    out_dir: Path,
    reason_code_namespaces: list[str] | None = None,
) -> None:
    """
    Write full SECURITY packet: coverage.json, coverage.md, reason_codes.md,
    deps_inventory.json, deps_inventory_runtime.json (SBOM-lite). Deterministic
    when policy files are unchanged; runtime inventory reflects installed env.
    """
    write_coverage(policy_root, out_dir)
    write_reason_codes_md(
        policy_root,
        out_dir,
        namespaces=reason_code_namespaces or ["TOOL", "COORD", "MEM", "ADV"],
    )
    write_deps_inventory(policy_root, out_dir)
    try:
        from labtrust_gym.security.deps_inventory import write_deps_inventory_runtime

        write_deps_inventory_runtime(out_dir, repo_root=policy_root)
    except Exception:
        pass
