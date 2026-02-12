"""
Unit tests for policy/llm/prompts.v0.2 loader and renderer.

- Load prompts.v0.2.yaml; render system content and user content.
- prompt_fingerprint = sha256(rendered_system + schema_version); stable for same content.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.policy.prompts_v02 import (
    compute_prompt_fingerprint_v02,
    get_rendered_system_content_v02,
    load_prompts_v02,
    render_prompt_v02,
    render_user_content_v02,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_load_prompts_v02() -> None:
    """Load policy/llm/prompts.v0.2.yaml; required keys present."""
    root = _repo_root()
    data = load_prompts_v02(repo_root=root)
    assert data["system_prompt"]
    assert data["developer_prompt"]
    assert "role_overlays" in data
    assert data["schema_version"] == "0.2"
    assert "ops" in data["role_overlays"] or "runner" in data["role_overlays"]


def test_get_rendered_system_content_v02() -> None:
    """Rendered system = system_prompt + developer_prompt + role_overlay(role_id)."""
    root = _repo_root()
    content, schema_version = get_rendered_system_content_v02(
        role_id="ROLE_RECEPTION", repo_root=root
    )
    assert "trusted" in content.lower() or "untrusted" in content.lower()
    assert schema_version == "0.2"


def test_compute_prompt_fingerprint_v02_stable() -> None:
    """Same rendered content + schema_version yields same fingerprint."""
    fp1 = compute_prompt_fingerprint_v02("system\ncontent", "0.2")
    fp2 = compute_prompt_fingerprint_v02("system\ncontent", "0.2")
    assert fp1 == fp2
    assert len(fp1) == 64
    assert all(c in "0123456789abcdef" for c in fp1)


def test_render_prompt_v02_returns_fingerprint() -> None:
    """render_prompt_v02 returns (system_content, user_content, prompt_fingerprint)."""
    root = _repo_root()
    system, user, fp = render_prompt_v02(
        role_id="ROLE_RECEPTION",
        partner_id="",
        state_summary={},
        allowed_actions=["NOOP", "TICK"],
        repo_root=root,
    )
    assert system
    assert "ALLOWED_ACTIONS" in user or "allowed_actions" in user.lower()
    assert len(fp) == 64
    assert fp == compute_prompt_fingerprint_v02(
        get_rendered_system_content_v02(role_id="ROLE_RECEPTION", repo_root=root)[0],
        "0.2",
    )


def test_render_user_content_v02_untrusted_block() -> None:
    """User content includes the UNTRUSTED_NOTES block."""
    out = render_user_content_v02(
        partner_id="p1",
        policy_fingerprint="fp",
        now_ts_s=0,
        timing_mode="explicit",
        role_id="ROLE_RECEPTION",
        state_summary_json="{}",
        allowed_actions_json="[]",
        untrusted_notes_json='[{"source":"specimen_note","text":"x"}]',
    )
    assert "UNTRUSTED" in out or "untrusted" in out
    assert "p1" in out
    assert "fp" in out
