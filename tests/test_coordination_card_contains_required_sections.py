"""
Assert that the rendered coordination benchmark card contains all sections
required for scientific review (scenario generation, scale configs, methods,
injections, metrics, determinism, limitations, fingerprint).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.studies.coordination_card import render_coordination_card


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


def test_coordination_card_fingerprint_block_not_placeholder() -> None:
    """Policy fingerprint block is replaced with actual fingerprint (no placeholder)."""
    repo = _repo_root()
    if not (repo / "policy" / "coordination").is_dir():
        pytest.skip("policy/coordination not found (not in repo root)")
    content = render_coordination_card(repo, include_file_hashes=True)
    assert "COORDINATION_POLICY_FINGERPRINT_PLACEHOLDER" not in content
    assert "SHA-256" in content or "sha256" in content.lower()
    assert "Fingerprint" in content
