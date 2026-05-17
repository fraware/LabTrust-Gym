"""Release manifest provenance guards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.deterministic import DETERMINISTIC_CERT_DIGEST, DETERMINISTIC_CERTIFICATE_ID
from labtrust_gym.pcs.manifest import PLACEHOLDER_COMMITS, validate_release_manifest
from labtrust_gym.pcs.mock_certificate import CERTIFYEDGE_SOURCE_REPO


def test_validate_release_manifest_rejects_placeholder_commits() -> None:
    with pytest.raises(ValueError, match="labtrust_gym_commit"):
        validate_release_manifest(
            {
                "mock_certificate": False,
                "labtrust_gym_commit": "local-dev",
                "certifyedge_commit": "a" * 40,
                "pcs_core_commit": "b" * 40,
                "certificate_source_repo": CERTIFYEDGE_SOURCE_REPO,
            }
        )


def test_validate_release_manifest_accepts_real_commits(release_dir: Path) -> None:
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    validate_release_manifest(manifest)
    for key in ("labtrust_gym_commit", "certifyedge_commit", "pcs_core_commit"):
        assert manifest[key] not in PLACEHOLDER_COMMITS


def test_release_certificate_not_mock_digest(release_dir: Path) -> None:
    cert = json.loads((release_dir / "trace_certificate.json").read_text(encoding="utf-8"))
    assert cert.get("signature_or_digest") != DETERMINISTIC_CERT_DIGEST
    assert cert.get("certificate_id") != DETERMINISTIC_CERTIFICATE_ID
