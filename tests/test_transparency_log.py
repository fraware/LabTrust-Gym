"""
Global transparency log: determinism (same inputs -> same root), Merkle inclusion
proof verification, and tamper detection (modified episode file -> proof fails).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from labtrust_gym.security.transparency import (
    build_merkle_tree,
    compute_episode_digest,
    discover_episodes,
    verify_merkle_proof,
    write_transparency_log,
)


def _minimal_artifact_dir(tmp_path: Path) -> Path:
    """Create minimal artifact layout: _repr/TaskA with results.json + episodes.jsonl."""
    repr_dir = tmp_path / "_repr" / "TaskA"
    repr_dir.mkdir(parents=True)
    results = {
        "schema_version": "0.2",
        "task": "TaskA",
        "seeds": [42],
        "episodes": [{"seed": 42, "metrics": {"throughput": 5, "steps": 100}}],
        "agent_baseline_id": "scripted_ops_v1",
    }
    (repr_dir / "results.json").write_text(json.dumps(results, sort_keys=True), encoding="utf-8")
    (repr_dir / "episodes.jsonl").write_text(
        '{"action_type":"CREATE_ACCESSION","t_s":10}\n', encoding="utf-8"
    )
    return tmp_path


def _artifact_with_bundle(tmp_path: Path) -> Path:
    """Create artifact with _repr and receipts/EvidenceBundle.v0.1 (manifest only)."""
    _minimal_artifact_dir(tmp_path)
    bundle_dir = tmp_path / "receipts" / "TaskA" / "EvidenceBundle.v0.1"
    bundle_dir.mkdir(parents=True)
    manifest = {
        "version": "0.1",
        "files": [{"path": "manifest.json", "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}],
        "policy_fingerprint": None,
        "partner_id": None,
        "policy_root_hash": None,
        "signature": None,
    }
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8"
    )
    return tmp_path


def test_discover_episodes() -> None:
    """discover_episodes finds _repr/<task> and optional EvidenceBundle."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _minimal_artifact_dir(Path(tmp))
        found = discover_episodes(root)
        assert len(found) == 1
        eid, results_path, episodes_path, bundle_dir = found[0]
        assert eid == "TaskA"
        assert (root / "_repr" / "TaskA" / "results.json") == results_path
        assert (root / "_repr" / "TaskA" / "episodes.jsonl") == episodes_path
        assert bundle_dir is None

    with tempfile.TemporaryDirectory() as tmp:
        root = _artifact_with_bundle(Path(tmp))
        found = discover_episodes(root)
        assert len(found) == 1
        _, _, _, bundle_dir = found[0]
        assert bundle_dir is not None
        assert (bundle_dir / "manifest.json").exists()


def test_determinism_same_inputs_same_root() -> None:
    """Same artifact -> same transparency log root (deterministic)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _artifact_with_bundle(Path(tmp))
        out1 = Path(tmp) / "out1"
        out2 = Path(tmp) / "out2"
        write_transparency_log(root, out1)
        write_transparency_log(root, out2)
        r1 = (out1 / "TRANSPARENCY_LOG" / "root.txt").read_text().strip()
        r2 = (out2 / "TRANSPARENCY_LOG" / "root.txt").read_text().strip()
        assert r1 == r2, "Same inputs must yield same Merkle root"


def test_inclusion_proof_verifies() -> None:
    """Merkle inclusion proof verifies for a random episode."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _artifact_with_bundle(Path(tmp))
        out = Path(tmp) / "out"
        write_transparency_log(root, out)
        log_dir = out / "TRANSPARENCY_LOG"
        root_hex = (log_dir / "root.txt").read_text().strip()
        log_data = json.loads((log_dir / "log.json").read_text(encoding="utf-8"))
        entries = log_data["entries"]
        assert entries
        # Proof file is proofs/TaskA.json (safe name)
        proof_path = log_dir / "proofs" / "TaskA.json"
        assert proof_path.exists(), f"Proof file expected at {proof_path}"
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        leaf_digest = entries[0]["digest"]
        assert verify_merkle_proof(leaf_digest, proof, root_hex), (
            "Inclusion proof must verify for episode digest"
        )


def test_tamper_proof_fails() -> None:
    """Tampering with one episode file yields different digest; original proof fails."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _artifact_with_bundle(Path(tmp))
        out = Path(tmp) / "out"
        write_transparency_log(root, out)
        log_dir = out / "TRANSPARENCY_LOG"
        root_hex = (log_dir / "root.txt").read_text().strip()
        proof_path = log_dir / "proofs" / "TaskA.json"
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        original_digest = proof["digest"]

        # Tamper: change results.json (one metric)
        results_path = root / "_repr" / "TaskA" / "results.json"
        data = json.loads(results_path.read_text(encoding="utf-8"))
        data["episodes"][0]["metrics"]["throughput"] = 999
        results_path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")

        # Recompute digest for same episode (same id, different content)
        from labtrust_gym.security.transparency import compute_episode_digest

        new_digest_entry = compute_episode_digest(
            "TaskA",
            data["episodes"][0],
            root / "_repr" / "TaskA" / "episodes.jsonl",
            root / "receipts" / "TaskA" / "EvidenceBundle.v0.1",
        )
        new_digest = new_digest_entry["digest"]
        assert new_digest != original_digest, "Tampered content must yield different digest"
        assert not verify_merkle_proof(new_digest, proof, root_hex), (
            "Original proof must fail for tampered digest"
        )
        # Original digest still verifies against original root
        assert verify_merkle_proof(original_digest, proof, root_hex)


def test_build_merkle_tree_empty() -> None:
    """Empty digests list yields empty root and no proofs."""
    root_hex, proofs = build_merkle_tree([])
    assert len(root_hex) == 64
    assert proofs == []


def test_build_merkle_tree_single() -> None:
    """Single digest: root equals that digest; proof has no siblings."""
    root_hex, proofs = build_merkle_tree(["a" * 64])
    assert root_hex == "a" * 64
    assert len(proofs) == 1
    assert proofs[0]["siblings"] == []


def test_verify_merkle_proof_two_leaves() -> None:
    """Two leaves: root = H(L||R); proof for L has sibling R on right."""
    d1 = "0" * 64
    d2 = "1" * 64
    root_hex, proofs = build_merkle_tree([d1, d2])
    assert verify_merkle_proof(d1, proofs[0], root_hex)
    assert verify_merkle_proof(d2, proofs[1], root_hex)
    assert not verify_merkle_proof(d2, proofs[0], root_hex)
