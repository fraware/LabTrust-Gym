"""
Safety case generator: claim -> control -> test(s) -> artifact(s) -> verification command.

Loads policy/safety_case/claims.v0.1.yaml and produces:
- SAFETY_CASE/safety_case.json (machine-readable)
- SAFETY_CASE/safety_case.md (human-readable)

Fully auto-generated; used in CI and paper_v0.1 artifact. Proves claims from the repo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from labtrust_gym.policy.loader import load_yaml

SAFETY_CASE_DIR = "SAFETY_CASE"
SAFETY_CASE_JSON = "safety_case.json"
SAFETY_CASE_MD = "safety_case.md"


def load_claims(policy_root: Path) -> dict[str, Any]:
    """Load safety case claims from policy/safety_case/claims.v0.1.yaml."""
    path = policy_root / "policy" / "safety_case" / "claims.v0.1.yaml"
    if not path.exists():
        return {"version": "0.1", "claims": []}
    data = load_yaml(path)
    out = (
        data.get("safety_case_claims", data) if isinstance(data, dict) else {"version": "0.1", "claims": []}
    )
    return cast(dict[str, Any], out)


def _claim_to_dict(c: dict[str, Any]) -> dict[str, Any]:
    """Normalize a claim for JSON output."""
    return {
        "claim_id": c.get("claim_id", ""),
        "statement": c.get("statement", ""),
        "controls": list(c.get("controls") or []),
        "tests": list(c.get("tests") or []),
        "artifacts": list(c.get("artifacts") or []),
        "commands": list(c.get("commands") or []),
    }


def build_safety_case(policy_root: Path) -> dict[str, Any]:
    """
    Build the full safety case structure: version, claims (each with claim_id, statement,
    controls, tests, artifacts, commands). Deterministic for same policy file.
    """
    claims_data = load_claims(policy_root)
    claims_list = claims_data.get("claims") or []
    return {
        "version": claims_data.get("version", "0.1"),
        "source": "policy/safety_case/claims.v0.1.yaml",
        "claims": [_claim_to_dict(c) for c in claims_list],
    }


def write_safety_case_md(safety_case: dict[str, Any], md_path: Path) -> None:
    """Write human-readable safety_case.md."""
    lines = [
        "# Safety case (auto-generated)",
        "",
        "Claim -> control -> test(s) -> artifact(s) -> verification command.",
        "Source: " + safety_case.get("source", ""),
        "",
        "---",
        "",
    ]
    for claim in safety_case.get("claims") or []:
        cid = claim.get("claim_id", "")
        stmt = claim.get("statement", "")
        lines.append(f"## {cid}")
        lines.append("")
        lines.append(f"**Statement:** {stmt}")
        lines.append("")
        controls = claim.get("controls") or []
        if controls:
            lines.append("**Controls:**")
            for c in controls:
                lines.append(f"- {c}")
            lines.append("")
        tests = claim.get("tests") or []
        if tests:
            lines.append("**Tests:**")
            for t in tests:
                lines.append(f"- `{t}`")
            lines.append("")
        artifacts = claim.get("artifacts") or []
        if artifacts:
            lines.append("**Artifacts:**")
            for a in artifacts:
                lines.append(f"- {a}")
            lines.append("")
        commands = claim.get("commands") or []
        if commands:
            lines.append("**Verification commands:**")
            for cmd in commands:
                lines.append(f"- `{cmd}`")
            lines.append("")
        lines.append("---")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def emit_safety_case(policy_root: Path, out_dir: Path) -> dict[str, Any]:
    """
    Write SAFETY_CASE/safety_case.json and SAFETY_CASE/safety_case.md under out_dir.
    Returns the safety_case dict.
    """
    out_dir = Path(out_dir)
    safety_dir = out_dir / SAFETY_CASE_DIR
    safety_dir.mkdir(parents=True, exist_ok=True)
    safety_case = build_safety_case(policy_root)
    json_path = safety_dir / SAFETY_CASE_JSON
    json_path.write_text(
        json.dumps(safety_case, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_safety_case_md(safety_case, safety_dir / SAFETY_CASE_MD)
    return safety_case


def get_claimed_tests(policy_root: Path) -> list[str]:
    """Return list of test module/path strings referenced in claims (for validation)."""
    claims_data = load_claims(policy_root)
    tests: list[str] = []
    for c in claims_data.get("claims") or []:
        for t in c.get("tests") or []:
            if t and t not in tests:
                tests.append(t)
    return tests


def get_claimed_artifacts(policy_root: Path) -> list[str]:
    """Return list of artifact paths referenced in claims (for paper layout validation)."""
    claims_data = load_claims(policy_root)
    artifacts: list[str] = []
    for c in claims_data.get("claims") or []:
        for a in c.get("artifacts") or []:
            if a and a not in artifacts:
                artifacts.append(a)
    return artifacts
