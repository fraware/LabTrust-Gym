#!/usr/bin/env python3
"""
Validate that security attack suite and safety case claims reference the same
risk and control IDs as the canonical sources. Run from repo root or set
LABTRUST_POLICY_DIR.

Checks:
- Every risk_id in security_attack_suite attacks exists in risk_registry.
- Every control string in safety case claims exists in the suite's controls
  (by control_id or name) or in the allowlist of known descriptive controls.

Exit 0 if all checks pass, 1 with error messages otherwise.
"""

from __future__ import annotations

import sys

# Allowlist for safety case control strings that are descriptive (no formal
# control_id in the suite). Document here to catch drift.
SAFETY_CASE_CONTROL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "Coordination security pack (scale x method x injection matrix)",
        "Runner output schema enforcement",
        "Golden runner validates contract",
        "Single RNG wrapper seeded per episode",
        "No ambient randomness in step",
        "validate-policy before release",
        "failure_models.v0.1 maintenance_schedule",
        "reagent_policy.v0.1 panel_requirements",
        "package-release paper_v0.1 pipeline",
    }
)


def main() -> int:
    try:
        from labtrust_gym.benchmarks.security_runner import load_attack_suite
        from labtrust_gym.config import get_repo_root
        from labtrust_gym.policy.loader import load_yaml
        from labtrust_gym.policy.risks import load_risk_registry
    except ImportError as e:
        print(f"Import error: {e}. Run from repo root with labtrust-gym installed.", file=sys.stderr)
        return 1

    repo_root = get_repo_root()
    policy_root = repo_root
    errors: list[str] = []

    # 1. Load risk registry
    risk_reg_path = repo_root / "policy" / "risks" / "risk_registry.v0.1.yaml"
    if not risk_reg_path.exists():
        errors.append(f"Risk registry not found: {risk_reg_path}")
        risk_ids = set()
    else:
        try:
            risk_registry = load_risk_registry(risk_reg_path)
            risk_ids = set(risk_registry.risks.keys())
        except Exception as e:
            errors.append(f"Failed to load risk registry: {e}")
            risk_ids = set()

    # 2. Load security attack suite
    try:
        suite = load_attack_suite(policy_root)
    except Exception as e:
        errors.append(f"Failed to load security attack suite: {e}")
        suite = {"controls": [], "attacks": []}

    controls_list = suite.get("controls") or []
    controls_by_id = {c["control_id"]: c for c in controls_list if c.get("control_id")}
    control_ids = set(controls_by_id.keys())
    control_names = {c.get("name", "").strip() for c in controls_list if c.get("name")}

    attacks = suite.get("attacks") or []
    attack_risk_ids = {a.get("risk_id") for a in attacks if a.get("risk_id")}

    # 3. Every risk_id in suite attacks must be in risk registry
    if risk_ids:
        for rid in attack_risk_ids:
            if rid and rid not in risk_ids:
                errors.append(f"Security attack suite references risk_id {rid!r} which is not in risk_registry")

    # 4. Load safety case claims
    claims_path = repo_root / "policy" / "safety_case" / "claims.v0.1.yaml"
    if not claims_path.exists():
        errors.append(f"Safety case claims not found: {claims_path}")
        claim_controls = set()
    else:
        try:
            data = load_yaml(claims_path)
            claims = data.get("safety_case_claims", data)
            if isinstance(claims, dict):
                claims = claims.get("claims", [])
            else:
                claims = []
            claim_controls = set()
            for c in claims:
                if not isinstance(c, dict):
                    continue
                for ctrl in c.get("controls") or []:
                    if isinstance(ctrl, str) and ctrl.strip():
                        claim_controls.add(ctrl.strip())
        except Exception as e:
            errors.append(f"Failed to load safety case claims: {e}")
            claim_controls = set()

    # 5. Every safety case control must be in suite (control_id or name) or allowlist
    for ctrl in claim_controls:
        if ctrl in control_ids:
            continue
        if ctrl in control_names:
            continue
        if ctrl in SAFETY_CASE_CONTROL_ALLOWLIST:
            continue
        errors.append(
            f"Safety case control {ctrl!r} is not in security_attack_suite controls "
            "(control_id or name) and not in allowlist. Add to suite or to "
            "SAFETY_CASE_CONTROL_ALLOWLIST in this script."
        )

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
