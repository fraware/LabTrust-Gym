"""
Assert that the rendered coordination benchmark card contains all sections
required for scientific review (scenario generation, scale configs, methods,
injections, metrics, determinism, limitations, fingerprint).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.studies.coordination_card import (
    render_coordination_card,
    render_coordination_llm_card,
    write_coordination_llm_card,
)

REQUIRED_SECTIONS = [
    "## Scope",
    "## Scenario generation",
    "## Scale configs",
    "## Methods",
    "## Injections",
    "## Metrics definitions",
    "## Determinism guarantees",
    "## What this benchmark is NOT measuring",
    "## Policy fingerprint",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_coordination_card_contains_required_sections() -> None:
    """Rendered COORDINATION_CARD has all required sections for scientific review."""
    repo = _repo_root()
    if not (repo / "policy" / "coordination").is_dir():
        pytest.skip("policy/coordination not found (not in repo root)")
    content = render_coordination_card(repo, include_file_hashes=True)
    for section in REQUIRED_SECTIONS:
        assert section in content, f"Missing required section: {section}"


def test_coordination_card_fingerprint_block_replaced() -> None:
    """Policy fingerprint block is replaced with actual fingerprint (token not left in output)."""
    repo = _repo_root()
    if not (repo / "policy" / "coordination").is_dir():
        pytest.skip("policy/coordination not found (not in repo root)")
    content = render_coordination_card(repo, include_file_hashes=True)
    assert "COORDINATION_POLICY_FINGERPRINT_TOKEN" not in content
    assert "SHA-256" in content or "sha256" in content.lower()
    assert "Fingerprint" in content


LLM_CARD_REQUIRED = [
    "## LLM coordination methods",
    "## Backends",
    "## Policy fingerprint",
    "## Injection coverage",
    "## Known limitations",
]


def test_coordination_llm_card_contains_required_sections() -> None:
    """Rendered COORDINATION_LLM_CARD has methods, backends, fingerprint, coverage, limitations."""
    repo = _repo_root()
    if not (repo / "policy" / "coordination").is_dir():
        pytest.skip("policy/coordination not found (not in repo root)")
    content = render_coordination_llm_card(repo)
    for section in LLM_CARD_REQUIRED:
        assert section in content, f"Missing required section: {section}"
    assert "llm_central_planner" in content
    assert "deterministic" in content


def test_write_coordination_llm_card_writes_file(tmp_path: Path) -> None:
    """write_coordination_llm_card writes COORDINATION_LLM_CARD.md with expected content."""
    repo = _repo_root()
    if not (repo / "policy" / "coordination").is_dir():
        pytest.skip("policy/coordination not found (not in repo root)")
    out = tmp_path / "COORDINATION_LLM_CARD.md"
    write_coordination_llm_card(out, repo)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "Coordination LLM Card" in text
    assert "openai_live" in text
