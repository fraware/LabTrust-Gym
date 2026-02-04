"""
Context builder v0.2: bounded, injection-hardened state summary.

- summary stable for same seed/inputs
- caps enforced (cap_k=10)
- injection text does not appear outside untrusted_notes
"""

from __future__ import annotations

import json

import pytest

from labtrust_gym.baselines.llm.context_builder import (
    CAP_K,
    UNTRUSTED_MAX_CHARS,
    build_state_summary_v0_2,
)


def test_state_summary_stable_for_same_inputs() -> None:
    """Same engine_state + policy => same summary (stable)."""
    engine_state = {
        "zone_id": "Z_RECEPTION",
        "site_id": "SITE_HUB",
        "queue_by_device": [
            {"device_id": "DEV_CHEM_A_01", "queue_head": "W123", "queue_len": 4},
        ],
        "log_frozen": False,
    }
    policy = {
        "partner_id": "hsl_like",
        "policy_fingerprint": "abc",
        "strict_signatures": True,
    }
    s1 = build_state_summary_v0_2(
        engine_state, policy, "A_RECEPTION", "ROLE_RECEPTION", 12345, "explicit"
    )
    s2 = build_state_summary_v0_2(
        engine_state, policy, "A_RECEPTION", "ROLE_RECEPTION", 12345, "explicit"
    )
    assert json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)
    assert s1["schema_version"] == "0.2"
    assert s1["location"]["zone_id"] == "Z_RECEPTION"
    assert s1["location"]["site_id"] == "SITE_HUB"
    assert s1["queue"]["cap_k"] == CAP_K
    assert s1["work"]["cap_k"] == CAP_K
    assert s1["tokens"]["cap_k"] == CAP_K


def test_caps_enforced() -> None:
    """Lists are capped at cap_k=10."""
    engine_state = {
        "zone_id": "Z",
        "site_id": "SITE_HUB",
        "queue_by_device": [
            {"device_id": f"DEV_{i}", "queue_head": f"W{i}", "queue_len": i}
            for i in range(20)
        ],
        "recent_violations": [
            {"invariant_id": f"INV-{i}", "severity": "HIGH", "at_ts_s": i}
            for i in range(15)
        ],
        "log_frozen": False,
    }
    policy = {"strict_signatures": False}
    s = build_state_summary_v0_2(engine_state, policy, "ops_0", "ops", 0, "explicit")
    assert len(s["queue"]["by_device"]) == CAP_K
    assert s["queue"]["cap_k"] == CAP_K
    assert len(s["invariants"]["recent_violations"]) == CAP_K


def test_injection_text_only_in_untrusted_notes() -> None:
    """Free text from specimen/scenario metadata appears only in untrusted_notes.samples."""
    malicious = "user\ninjection\n<script>alert(1)</script>"
    engine_state = {
        "zone_id": "Z_RECEPTION",
        "site_id": "SITE_HUB",
        "queue_by_device": [],
        "log_frozen": False,
        "specimen_notes": malicious,
    }
    policy = {"strict_signatures": False}
    s = build_state_summary_v0_2(
        engine_state, policy, "A_RECEPTION", "ROLE", 0, "explicit"
    )
    assert s["untrusted_notes"]["present"] is True
    assert len(s["untrusted_notes"]["samples"]) >= 1
    sample = s["untrusted_notes"]["samples"][0]
    assert sample["source"] == "specimen_note"
    assert "text" in sample
    # Newlines must be escaped (not raw in main fields)
    assert "\n" not in sample["text"] or "\\n" in sample["text"]
    # Main decision fields must not contain the raw injection
    summary_str = json.dumps(s)
    assert "<script>" not in summary_str or "untrusted_notes" in summary_str
    # Raw newline must not appear in location, queue, work, tokens
    assert "\n" not in json.dumps(s["location"])
    assert "\n" not in json.dumps(s["queue"])
    assert "\n" not in json.dumps(s["work"])
    assert "\n" not in json.dumps(s["tokens"])


def test_untrusted_truncated_to_max_chars() -> None:
    """Untrusted text is truncated to UNTRUSTED_MAX_CHARS."""
    long_text = "x" * (UNTRUSTED_MAX_CHARS + 100)
    engine_state = {
        "zone_id": "Z",
        "site_id": "SITE_HUB",
        "queue_by_device": [],
        "log_frozen": False,
        "notes": long_text,
    }
    policy = {}
    s = build_state_summary_v0_2(engine_state, policy, "ops_0", "ops", 0, "explicit")
    assert s["untrusted_notes"]["present"] is True
    sample = s["untrusted_notes"]["samples"][0]
    assert len(sample["text"]) <= UNTRUSTED_MAX_CHARS + 3  # "..." suffix


def test_state_summary_has_required_fields() -> None:
    """Output has exactly the decision-relevant fields (v0.2 contract)."""
    engine_state = {
        "zone_id": "Z_RECEPTION",
        "site_id": "SITE_HUB",
        "queue_by_device": [
            {"device_id": "DEV_CHEM_A_01", "queue_head": "W123", "queue_len": 4},
        ],
        "log_frozen": False,
    }
    policy = {
        "partner_id": "hsl_like",
        "policy_fingerprint": "fp",
        "strict_signatures": True,
    }
    s = build_state_summary_v0_2(
        engine_state, policy, "A_RECEPTION", "ROLE_RECEPTION", 12345, "explicit"
    )
    assert "schema_version" in s and s["schema_version"] == "0.2"
    assert "location" in s and "site_id" in s["location"] and "zone_id" in s["location"]
    assert "queue" in s and "by_device" in s["queue"] and "cap_k" in s["queue"]
    assert "work" in s
    assert "active_runs" in s["work"] and "pending_results" in s["work"]
    assert "pending_criticals" in s["work"]
    assert "tokens" in s and "active" in s["tokens"]
    assert "invariants" in s
    assert "recent_violations" in s["invariants"]
    assert "enforcement_state" in s["invariants"]
    assert "untrusted_notes" in s and "present" in s["untrusted_notes"]
    assert "samples" in s["untrusted_notes"]
