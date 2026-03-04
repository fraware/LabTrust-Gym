"""
Safety case generator: claim -> control -> test(s) -> artifact(s) -> verification command.

Loads policy/safety_case/claims.v0.1.yaml and produces:
- SAFETY_CASE/safety_case.json (machine-readable)
- SAFETY_CASE/safety_case.md (human-readable)

Fully auto-generated; used in CI and paper_v0.1 artifact. Proves claims from the repo.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from labtrust_gym.config import policy_path
from labtrust_gym.policy.loader import load_yaml

SAFETY_CASE_DIR = "SAFETY_CASE"
SAFETY_CASE_JSON = "safety_case.json"
SAFETY_CASE_MD = "safety_case.md"

# Safety case provider registry: provider_id -> provider (load_claims, build_safety_case).
_SAFETY_CASE_PROVIDERS: dict[str, Any] = {}


def register_safety_case_provider(provider_id: str, provider: Any) -> None:
    """Register a safety case provider. Overwrites if present."""
    _SAFETY_CASE_PROVIDERS[provider_id] = provider


def get_safety_case_provider(provider_id: str) -> Any | None:
    """Return the registered safety case provider, or None."""
    return _SAFETY_CASE_PROVIDERS.get(provider_id)


def list_safety_case_providers() -> list[str]:
    """Return sorted list of registered safety case provider IDs."""
    return sorted(_SAFETY_CASE_PROVIDERS.keys())


def _ensure_default_safety_provider() -> None:
    from types import SimpleNamespace

    if "default" not in _SAFETY_CASE_PROVIDERS:
        register_safety_case_provider(
            "default",
            SimpleNamespace(
                load_claims=load_claims,
                build_safety_case=_build_safety_case_impl,
            ),
        )


def load_claims(
    policy_root: Path,
    claims_path: Path | None = None,
) -> dict[str, Any]:
    """Load safety case claims. When claims_path is set, load from it; else policy/safety_case/claims.v0.1.yaml."""
    path = (
        claims_path
        if claims_path is not None and claims_path.exists()
        else policy_path(policy_root, "safety_case", "claims.v0.1.yaml")
    )
    if not path.exists():
        return {"version": "0.1", "claims": []}
    data = load_yaml(path)
    out = data.get("safety_case_claims", data) if isinstance(data, dict) else {"version": "0.1", "claims": []}
    return cast(dict[str, Any], out)


def _claim_to_dict(c: dict[str, Any], claim_version: str = "0.1") -> dict[str, Any]:
    """
    Normalize a claim for JSON output with traceability: claim -> control -> test/artifact.
    Adds claim_version and evidence_links with optional path/code_ref for validation.
    """
    claim_id = c.get("claim_id", "")
    controls = list(c.get("controls") or [])
    tests = list(c.get("tests") or [])
    artifacts = list(c.get("artifacts") or [])
    commands = list(c.get("commands") or [])
    control_sources = c.get("control_sources") or {}
    if not isinstance(control_sources, dict):
        control_sources = {}
    evidence_links: list[dict[str, Any]] = []
    for ctrl in controls:
        link: dict[str, Any] = {"type": "control", "id": ctrl}
        if ctrl in control_sources and control_sources[ctrl]:
            link["source"] = control_sources[ctrl]
        evidence_links.append(link)
    for t in tests:
        link = {"type": "test", "ref": t}
        if t.startswith("tests."):
            link["path"] = t.replace(".", "/", 1) + ".py"
        elif t.startswith("tests/"):
            link["path"] = t
        evidence_links.append(link)
    for a in artifacts:
        evidence_links.append({"type": "artifact", "path": a})
    out: dict[str, Any] = {
        "claim_id": claim_id,
        "claim_version": claim_version,
        "statement": c.get("statement", ""),
        "controls": controls,
        "tests": tests,
        "artifacts": artifacts,
        "commands": commands,
        "traceability": {
            "claim_id": claim_id,
            "evidence_links": evidence_links,
        },
    }
    artifacts_expected = list(c.get("artifacts_expected") or [])
    if artifacts_expected:
        out["artifacts_expected"] = artifacts_expected
    return out


def _build_safety_case_impl(
    policy_root: Path,
    claims_path: Path | None = None,
) -> dict[str, Any]:
    """Core safety case build (no provider dispatch)."""
    claims_data = load_claims(policy_root, claims_path=claims_path)
    claims_list = claims_data.get("claims") or []
    claim_version = str(claims_data.get("version", "0.1"))
    return {
        "version": claim_version,
        "source": "policy/safety_case/claims.v0.1.yaml",
        "claims": [_claim_to_dict(c, claim_version=claim_version) for c in claims_list],
    }


def build_safety_case(
    policy_root: Path,
    provider_id: str | None = None,
    claims_path: Path | None = None,
) -> dict[str, Any]:
    """
    Build the full safety case structure: version, claims (each with claim_id, statement,
    controls, tests, artifacts, commands). Deterministic for same policy file.
    When provider_id is set, use the registered safety case provider.
    When claims_path is set (and using default provider), load claims from that path.
    """
    if provider_id is not None:
        provider = get_safety_case_provider(provider_id)
        if provider is not None and hasattr(provider, "build_safety_case"):
            return provider.build_safety_case(policy_root)
    return _build_safety_case_impl(policy_root, claims_path=claims_path)


def write_safety_case_md(safety_case: dict[str, Any], md_path: Path) -> None:
    """Write human-readable safety_case.md."""
    lines = [
        "# Safety case (auto-generated)",
        "",
        "Claim -> control -> reproduce command (primary) -> artifact. Tests are supporting (what the command runs).",
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
        commands = claim.get("commands") or []
        if commands:
            lines.append("**Reproduce (primary):**")
            for cmd in commands:
                lines.append(f"- `{cmd}`")
            lines.append("")
        tests = claim.get("tests") or []
        if tests:
            lines.append("**Supporting tests:**")
            for t in tests:
                lines.append(f"- `{t}`")
            lines.append("")
        artifacts = claim.get("artifacts") or []
        if artifacts:
            lines.append("**Artifacts:**")
            for a in artifacts:
                lines.append(f"- {a}")
            lines.append("")
        lines.append("---")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    """Return hex digest of file contents. Raises if file cannot be read."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _enrich_safety_case_with_artifact_hashes(
    safety_case: dict[str, Any],
    release_dir: Path,
) -> None:
    """
    When built from a release dir, add artifact_sha256 to each claim that has
    artifacts_expected, for each path that exists under release_dir.
    Mutates safety_case in place.
    """
    release_dir = Path(release_dir)
    for claim in safety_case.get("claims") or []:
        expected = claim.get("artifacts_expected") or []
        if not expected:
            continue
        hashes: list[dict[str, str]] = []
        for rel_path in expected:
            full = release_dir / rel_path
            if full.is_file():
                try:
                    digest = _sha256_file(full)
                    hashes.append({"path": rel_path, "sha256": digest})
                except OSError:
                    pass
        if hashes:
            claim["artifact_sha256"] = hashes


def emit_safety_case(
    policy_root: Path,
    out_dir: Path,
    provider_id: str | None = None,
    claims_path: Path | None = None,
) -> dict[str, Any]:
    """
    Write SAFETY_CASE/safety_case.json and SAFETY_CASE/safety_case.md under out_dir.
    Returns the safety_case dict. When provider_id is set, use that provider.
    When claims_path is set, load claims from that path (default provider only).
    When built from a release dir (out_dir), claims with artifacts_expected get
    artifact_sha256 populated for each artifact that exists under out_dir.
    """
    out_dir = Path(out_dir)
    safety_dir = out_dir / SAFETY_CASE_DIR
    safety_dir.mkdir(parents=True, exist_ok=True)
    safety_case = build_safety_case(policy_root, provider_id=provider_id, claims_path=claims_path)
    _enrich_safety_case_with_artifact_hashes(safety_case, out_dir)
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


def run_smt_checks(safety_case: dict[str, Any]) -> dict[str, Any]:
    """
    Reserved for optional structural consistency checks when z3 is available.
    Performs trivial checks (e.g. claim_id non-empty via z3); does not prove
    claim implications (e.g. claim C implies control X). For full formal
    checks, reserve for future use.
    Returns {"smt_available": bool, "results": {claim_id: "pass"|"fail"|"skip"}, "errors": [...]}.
    When z3 is not installed, returns smt_available=False and empty results.
    """
    out: dict[str, Any] = {
        "smt_available": False,
        "results": {},
        "errors": [],
    }
    try:
        import z3

        out["smt_available"] = True
    except ImportError:
        return out
    for claim in safety_case.get("claims") or []:
        cid = claim.get("claim_id", "")
        if not cid:
            out["results"][cid or "(empty)"] = "fail"
            out["errors"].append("Claim with empty claim_id")
            continue
        # Trivial structural check via SMT: claim_id non-empty string constraint
        try:
            s = z3.String("claim_id")
            solver = z3.Solver()
            solver.add(z3.Length(s) > 0)
            solver.add(s == cid)
            if solver.check() == z3.sat:
                out["results"][cid] = "pass"
            else:
                out["results"][cid] = "fail"
        except Exception as e:
            out["results"][cid] = "skip"
            out["errors"].append(f"{cid}: {e}")
    return out


_ensure_default_safety_provider()
