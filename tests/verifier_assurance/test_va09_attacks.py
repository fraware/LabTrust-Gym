"""LT-VA-09 attack access-class leakage tests."""

from __future__ import annotations

import pytest

from labtrust_gym.verifier_assurance.attacks.access import (
    AccessClass,
    AttackAccessError,
    open_attack_handle,
)
from labtrust_gym.verifier_assurance.oracle.dual_oracle import (
    PublicVerifier,
    default_public_profile,
)


def test_cross_class_leakage_negative() -> None:
    pub = PublicVerifier(default_public_profile())
    black = open_attack_handle(AccessClass.BLACK_BOX, pub)
    with pytest.raises(AttackAccessError):
        black.as_white_box()
    with pytest.raises(AttackAccessError):
        black.verifier_internals()
    white = open_attack_handle(
        AccessClass.WHITE_BOX,
        pub,
        verifier_profile=default_public_profile(),
    )
    internals = white.verifier_internals()
    assert internals["role"] == "public"


def test_query_logging_completeness() -> None:
    pub = PublicVerifier(default_public_profile())
    handle = open_attack_handle(AccessClass.BLACK_BOX, pub)
    state = {
        "result_released": True,
        "qc": {"results": {"R1": {"status": "released", "flags": []}}, "device_qc_state": {}},
    }
    handle.query_verifier(state)
    handle.query_verifier(state)
    assert len(handle.query_log) == 2
    assert handle.query_log[0]["access_class"] == "black_box"
    assert "decision" in handle.query_log[0]
