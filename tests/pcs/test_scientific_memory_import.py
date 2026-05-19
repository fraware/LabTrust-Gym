"""Scientific Memory import alignment checks."""

from __future__ import annotations

import json

import pytest

from labtrust_gym.pcs.scientific_memory_import import (
    SCIENTIFIC_MEMORY_CLAIM_ID_MISMATCH,
    assert_scientific_memory_import_alignment,
    certified_claim_id,
    materialize_downstream_release_artifacts,
)


def test_assert_scientific_memory_import_alignment_passes(
    repo_root: Path, release_dir: Path, tmp_path: Path
) -> None:
    from shutil import copytree

    root = tmp_path / "release"
    copytree(release_dir, root, dirs_exist_ok=True)
    materialize_downstream_release_artifacts(root, policy_root=repo_root)
    assert_scientific_memory_import_alignment(root)


def test_assert_scientific_memory_import_alignment_rejects_tamper(
    repo_root: Path, release_dir: Path, tmp_path: Path,
) -> None:
    from shutil import copytree

    case = tmp_path / "case"
    copytree(release_dir, case, dirs_exist_ok=True)
    materialize_downstream_release_artifacts(case, policy_root=repo_root)
    signed_path = case / "signed_science_claim_bundle.json"
    signed = json.loads(signed_path.read_text(encoding="utf-8"))
    bundle = signed.setdefault("science_claim_bundle", signed)
    bundle.setdefault("claim_artifact", {})["artifact_id"] = "claim-tampered"
    signed_path.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=SCIENTIFIC_MEMORY_CLAIM_ID_MISMATCH):
        assert_scientific_memory_import_alignment(case)


def test_certified_claim_id_matches_release(release_dir: Path) -> None:
    if not (release_dir / "science_claim_bundle.certified.json").is_file():
        pytest.skip("release fixtures not populated")
    assert certified_claim_id(release_dir) == "claim-pcs-qc-release-v0.1"
