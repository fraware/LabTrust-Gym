"""Certificate attachment integrity (trace_hash alignment)."""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.pcs.attach_certificate import attach_trace_certificate
from labtrust_gym.pcs.export import export_pcs_bundle


def test_attach_certificate_rejects_trace_hash_mismatch(valid_run: Path, tmp_path: Path) -> None:
    bundle = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    bad_cert = {
        "certificate_id": "cert-bad",
        "schema_version": "v0",
        "trace_hash": "sha256:" + "0" * 64,
    }
    with pytest.raises(ValueError, match="trace_hash"):
        attach_trace_certificate(bundle, bad_cert)
