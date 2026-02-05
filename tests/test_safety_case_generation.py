"""
Safety case generation: claim -> control -> test(s) -> artifact(s) -> command.

- All referenced tests in policy/safety_case/claims.v0.1.yaml exist.
- Generator produces SAFETY_CASE/safety_case.json and safety_case.md.
- paper_v0.1 output layout includes SAFETY_CASE/ (tested in test_package_release).
- Proof from repo: safety_case.md is consistent with repo state (generated from claims).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from labtrust_gym.config import get_repo_root
from labtrust_gym.security.safety_case import (
    build_safety_case,
    emit_safety_case,
    get_claimed_artifacts,
    get_claimed_tests,
    load_claims,
)


def _test_module_to_path(module: str) -> Path:
    """Map tests.test_foo_bar -> tests/test_foo_bar.py."""
    if not module.startswith("tests."):
        return Path(module.replace(".", "/") + ".py")
    rest = module[len("tests.") :]
    return Path("tests") / (rest.replace(".", "_") + ".py")


def test_all_referenced_tests_exist() -> None:
    """Every test referenced in claims.v0.1.yaml has a corresponding test file in the repo."""
    root = get_repo_root()
    claimed = get_claimed_tests(root)
    assert claimed, "claims.v0.1.yaml must reference at least one test"
    missing = []
    for mod in claimed:
        # Module "tests.test_golden_suite" -> file tests/test_golden_suite.py
        path = _test_module_to_path(mod)
        full = root / path
        if not full.exists():
            missing.append(str(path))
    assert not missing, (
        f"Claims reference test modules whose files are missing: {missing}. "
        "Add the test files or update policy/safety_case/claims.v0.1.yaml."
    )


def test_safety_case_emit_produces_json_and_md() -> None:
    """emit_safety_case creates SAFETY_CASE/safety_case.json and safety_case.md with expected structure."""
    root = get_repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        result = emit_safety_case(policy_root=root, out_dir=out_dir)
        safety_dir = out_dir / "SAFETY_CASE"
        json_path = safety_dir / "safety_case.json"
        md_path = safety_dir / "safety_case.md"
        assert json_path.exists(), "safety_case.json must be written"
        assert md_path.exists(), "safety_case.md must be written"
        assert "version" in result
        assert "claims" in result
        assert "source" in result
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        assert loaded["version"] == result["version"]
        assert len(loaded["claims"]) == len(result["claims"])
        md_content = md_path.read_text(encoding="utf-8")
        assert "Safety case (auto-generated)" in md_content
        assert "claim" in md_content.lower() or "Claim" in md_content


def test_claimed_artifacts_referenced_in_layout() -> None:
    """Every claimed artifact is either under repo (policy, etc.) or a known paper_v0.1 output path."""
    root = get_repo_root()
    artifacts = get_claimed_artifacts(root)
    assert artifacts, "claims must reference at least one artifact"
    # Paper output paths that are created by package-release paper_v0.1
    paper_output_paths = {
        "SECURITY/",
        "receipts/",
        "TABLES/",
        "FIGURES/",
        "SAFETY_CASE/",
        "RELEASE_NOTES.md",
        "_repr/",
    }
    for a in artifacts:
        # Normalize: artifact may be "SAFETY_CASE/safety_case.json" or "SECURITY/"
        top = a.split("/")[0] if "/" in a else a
        in_paper = (a + "/" if not a.endswith("/") else a) in paper_output_paths or (
            top + "/"
        ) in paper_output_paths or a in paper_output_paths
        in_repo = (root / a).exists() or (root / top).exists()
        assert in_paper or in_repo, (
            f"Claimed artifact {a!r} is neither under repo nor in paper_v0.1 layout. "
            "Add to package_release output or policy."
        )


def test_build_safety_case_deterministic() -> None:
    """build_safety_case returns same structure for same policy root (deterministic)."""
    root = get_repo_root()
    a = build_safety_case(root)
    b = build_safety_case(root)
    assert a["version"] == b["version"]
    assert a["source"] == b["source"]
    assert len(a["claims"]) == len(b["claims"])
    for i, (ca, cb) in enumerate(zip(a["claims"], b["claims"])):
        assert ca["claim_id"] == cb["claim_id"], f"claim {i} id mismatch"
        assert ca["statement"] == cb["statement"], f"claim {i} statement mismatch"


def test_load_claims_returns_expected_structure() -> None:
    """load_claims returns dict with version and claims list."""
    root = get_repo_root()
    data = load_claims(root)
    assert isinstance(data, dict)
    assert "claims" in data
    assert isinstance(data["claims"], list)
    for c in data["claims"]:
        assert "claim_id" in c
        assert "statement" in c
        assert "controls" in c or "tests" in c or "artifacts" in c or "commands" in c


def test_safety_case_md_consistent_with_claims() -> None:
    """Regenerated safety_case.md contains every claim_id from claims (proof from repo)."""
    root = get_repo_root()
    data = load_claims(root)
    claim_ids = [c.get("claim_id", "") for c in (data.get("claims") or []) if c.get("claim_id")]
    assert claim_ids, "claims must define at least one claim_id"
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        emit_safety_case(policy_root=root, out_dir=out_dir)
        md_path = out_dir / "SAFETY_CASE" / "safety_case.md"
        assert md_path.exists(), "safety_case.md must be written"
        md_content = md_path.read_text(encoding="utf-8")
    for cid in claim_ids:
        assert cid in md_content, (
            f"Generated safety_case.md must contain claim_id {cid!r} (consistent with claims)"
        )
