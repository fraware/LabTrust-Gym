"""pcs-core canonical hash vector parity (Phase 2 PR 3)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("pcs_core")

from pcs_core.hash import canonical_hash
from pcs_core.hash_vectors import verify_vectors

from labtrust_gym.pcs.hash import hash_vector_dir, pcs_digest, pcs_digest_ignoring_signature


def test_pcs_core_hash_vectors_verify() -> None:
    drift = verify_vectors()
    assert drift == [], f"pcs-core hash vector drift: {drift}"


def test_labtrust_hash_matches_pcs_core_runtime_receipt_vector() -> None:
    vector_dir = hash_vector_dir("RuntimeReceipt.v0")
    data = json.loads((vector_dir / "input.json").read_text(encoding="utf-8"))
    expected = (vector_dir / "digest.txt").read_text(encoding="utf-8").strip()
    assert pcs_digest(data) == expected
    assert canonical_hash(data) == expected


def test_labtrust_hash_matches_pcs_core_certified_bundle_vector() -> None:
    vector_dir = hash_vector_dir("ScienceClaimBundle.v0")
    data = json.loads((vector_dir / "input.json").read_text(encoding="utf-8"))
    expected = (vector_dir / "digest.txt").read_text(encoding="utf-8").strip()
    assert pcs_digest(data) == expected


def test_labtrust_hash_ignores_signature_or_digest() -> None:
    vector_dir = hash_vector_dir("RuntimeReceipt.v0")
    data = json.loads((vector_dir / "input.json").read_text(encoding="utf-8"))
    with_sig = dict(data)
    with_sig["signature_or_digest"] = "sha256:" + "f" * 64
    assert pcs_digest_ignoring_signature(with_sig) == pcs_digest(data)
