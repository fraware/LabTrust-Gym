"""Unit tests for PCS QC-release workflow policy evaluation."""

from __future__ import annotations

from labtrust_gym.pcs.workflow import INITIAL_STATE, evaluate_action


def test_release_without_qc_denied() -> None:
    state = {**INITIAL_STATE, "lifecycle": "analyzed", "qc_complete": False}
    decision, reason, _ = evaluate_action("release_sample", state, "release_manager")
    assert decision == "deny"
    assert reason == "missing_qc"


def test_release_by_non_release_role_denied() -> None:
    state = {
        **INITIAL_STATE,
        "lifecycle": "analyzed",
        "qc_complete": True,
        "analysis_complete": True,
    }
    decision, reason, _ = evaluate_action("release_sample", state, "analyst")
    assert decision == "deny"
    assert reason == "unauthorized_release"


def test_valid_release_path_allowed() -> None:
    state = {
        **INITIAL_STATE,
        "lifecycle": "analyzed",
        "qc_complete": True,
        "analysis_complete": True,
    }
    decision, reason, post = evaluate_action("release_sample", state, "release_manager")
    assert decision == "allow"
    assert reason == "ok"
    assert post["released"] is True
    assert post["lifecycle"] == "released"
