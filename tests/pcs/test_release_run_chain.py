"""release_run certificate-id chain rejects stale PF signed bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.release_run import validate_certificate_id_chain


def test_validate_certificate_id_chain_rejects_stale_signed_bundle(tmp_path: Path) -> None:
    certified = {
        "bundle_id": "scb-test",
        "certificates": [{"certificate_id": "cert-trace-current", "trace_hash": "sha256:aa"}],
        "runtime_receipts": [{"trace_hash": "sha256:aa"}],
    }
    signed = {
        "science_claim_bundle": {
            "certificates": [{"certificate_id": "cert-trace-stale-old"}],
        }
    }
    (tmp_path / "science_claim_bundle.certified.json").write_text(
        json.dumps(certified), encoding="utf-8"
    )
    (tmp_path / "signed_science_claim_bundle.json").write_text(json.dumps(signed), encoding="utf-8")

    with pytest.raises(ValueError, match="stale PF sign input"):
        validate_certificate_id_chain(tmp_path)
