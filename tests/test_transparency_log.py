"""
Global transparency log: determinism (same inputs -> same root), Merkle inclusion
proof verification, and tamper detection (modified episode file -> proof fails).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from labtrust_gym.security.transparency import (
    LLM_LIVE_TRANSPARENCY_VERSION,
    build_merkle_tree,
    collect_llm_live_metadata_from_pack,
    discover_episodes,
    verify_merkle_proof,
    write_llm_live_transparency_log,
    write_transparency_log,
)


def _minimal_artifact_dir(tmp_path: Path) -> Path:
    """Create minimal artifact layout: _repr/throughput_sla with results.json + episodes.jsonl."""
    repr_dir = tmp_path / "_repr" / "throughput_sla"
    repr_dir.mkdir(parents=True)
    results = {
        "schema_version": "0.2",
        "task": "throughput_sla",
        "seeds": [42],
        "episodes": [{"seed": 42, "metrics": {"throughput": 5, "steps": 100}}],
        "agent_baseline_id": "scripted_ops_v1",
    }
    (repr_dir / "results.json").write_text(json.dumps(results, sort_keys=True), encoding="utf-8")
    (repr_dir / "episodes.jsonl").write_text('{"action_type":"CREATE_ACCESSION","t_s":10}\n', encoding="utf-8")
    return tmp_path


def _artifact_with_bundle(tmp_path: Path) -> Path:
    """Create artifact with _repr and receipts/EvidenceBundle.v0.1 (manifest only)."""
    _minimal_artifact_dir(tmp_path)
    bundle_dir = tmp_path / "receipts" / "throughput_sla" / "EvidenceBundle.v0.1"
    bundle_dir.mkdir(parents=True)
    manifest = {
        "version": "0.1",
        "files": [
            {
                "path": "manifest.json",
                "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            }
        ],
        "policy_fingerprint": None,
        "partner_id": None,
        "policy_root_hash": None,
        "signature": None,
    }
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return tmp_path


def test_discover_episodes() -> None:
    """discover_episodes finds _repr/<task> and optional EvidenceBundle."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _minimal_artifact_dir(Path(tmp))
        found = discover_episodes(root)
        assert len(found) == 1
        eid, results_path, episodes_path, bundle_dir = found[0]
        assert eid == "throughput_sla"
        assert (root / "_repr" / "throughput_sla" / "results.json") == results_path
        assert (root / "_repr" / "throughput_sla" / "episodes.jsonl") == episodes_path
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
        # Proof file is proofs/throughput_sla.json (safe name)
        proof_path = log_dir / "proofs" / "throughput_sla.json"
        assert proof_path.exists(), f"Proof file expected at {proof_path}"
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        leaf_digest = entries[0]["digest"]
        assert verify_merkle_proof(leaf_digest, proof, root_hex), "Inclusion proof must verify for episode digest"


def test_tamper_proof_fails() -> None:
    """Tampering with one episode file yields different digest; original proof fails."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _artifact_with_bundle(Path(tmp))
        out = Path(tmp) / "out"
        write_transparency_log(root, out)
        log_dir = out / "TRANSPARENCY_LOG"
        root_hex = (log_dir / "root.txt").read_text().strip()
        proof_path = log_dir / "proofs" / "throughput_sla.json"
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        original_digest = proof["digest"]

        # Tamper: change results.json (one metric)
        results_path = root / "_repr" / "throughput_sla" / "results.json"
        data = json.loads(results_path.read_text(encoding="utf-8"))
        data["episodes"][0]["metrics"]["throughput"] = 999
        results_path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")

        # Recompute digest for same episode (same id, different content)
        from labtrust_gym.security.transparency import compute_episode_digest

        new_digest_entry = compute_episode_digest(
            "throughput_sla",
            data["episodes"][0],
            root / "_repr" / "throughput_sla" / "episodes.jsonl",
            root / "receipts" / "throughput_sla" / "EvidenceBundle.v0.1",
        )
        new_digest = new_digest_entry["digest"]
        assert new_digest != original_digest, "Tampered content must yield different digest"
        assert not verify_merkle_proof(new_digest, proof, root_hex), "Original proof must fail for tampered digest"
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


# --- LLM live transparency log (pack output: hashes, fingerprint, latency/cost) ---


def test_collect_llm_live_metadata_empty_dir() -> None:
    """collect_llm_live_metadata_from_pack with no baselines/results returns empty structure."""
    with tempfile.TemporaryDirectory() as tmp:
        pack_dir = Path(tmp)
        out = collect_llm_live_metadata_from_pack(pack_dir)
    assert out["version"] == LLM_LIVE_TRANSPARENCY_VERSION
    assert out["prompt_hashes"] == []
    assert out["tool_registry_fingerprint"] is None
    assert out["model_version_identifiers"] == {}
    assert out["latency_and_cost_statistics"] == {}
    assert out["per_task"] == {}


def test_collect_llm_live_metadata_from_results() -> None:
    """collect_llm_live_metadata_from_pack aggregates metadata from baselines/results/*.json."""
    with tempfile.TemporaryDirectory() as tmp:
        pack_dir = Path(tmp)
        results_dir = pack_dir / "baselines" / "results"
        results_dir.mkdir(parents=True)
        (results_dir / "throughput_sla_scripted_ops.json").write_text(
            json.dumps(
                {
                    "task": "throughput_sla",
                    "metadata": {
                        "prompt_sha256": "abc123",
                        "llm_backend_id": "openai_responses",
                        "llm_model_id": "gpt-4o-mini",
                        "mean_llm_latency_ms": 100.0,
                        "p95_llm_latency_ms": 200.0,
                        "total_tokens": 500,
                        "estimated_cost_usd": 0.001,
                    },
                    "tool_registry_fingerprint": "fp_xyz",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (results_dir / "stat_insertion_scripted_ops.json").write_text(
            json.dumps(
                {
                    "task": "stat_insertion",
                    "metadata": {
                        "prompt_sha256": "def456",
                        "llm_model_id": "gpt-4o-mini",
                        "mean_llm_latency_ms": 150.0,
                    },
                    "tool_registry_fingerprint": "fp_xyz",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        out = collect_llm_live_metadata_from_pack(pack_dir)
    assert out["version"] == LLM_LIVE_TRANSPARENCY_VERSION
    assert sorted(out["prompt_hashes"]) == ["abc123", "def456"]
    assert out["tool_registry_fingerprint"] == "fp_xyz"
    assert out["model_version_identifiers"]["llm_backend_id"] == "openai_responses"
    assert out["model_version_identifiers"]["llm_model_id"] == "gpt-4o-mini"
    assert "mean_latency_ms" in out["latency_and_cost_statistics"]
    stats = out["latency_and_cost_statistics"]["mean_latency_ms"]
    assert stats["min"] == 100.0 and stats["max"] == 150.0 and stats["mean"] == 125.0
    assert "throughput_sla" in out["per_task"] and "stat_insertion" in out["per_task"]


def test_write_llm_live_transparency_log() -> None:
    """write_llm_live_transparency_log creates TRANSPARENCY_LOG/llm_live.json with canonical content."""
    with tempfile.TemporaryDirectory() as tmp:
        pack_dir = Path(tmp)
        (pack_dir / "baselines" / "results").mkdir(parents=True)
        (pack_dir / "baselines" / "results" / "throughput_sla.json").write_text(
            json.dumps({"task": "throughput_sla", "metadata": {"prompt_sha256": "h0"}}, sort_keys=True),
            encoding="utf-8",
        )
        log_dir = write_llm_live_transparency_log(pack_dir)
        assert log_dir == pack_dir / "TRANSPARENCY_LOG"
        out_path = log_dir / "llm_live.json"
        assert out_path.exists()
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert data["version"] == LLM_LIVE_TRANSPARENCY_VERSION
        assert data["prompt_hashes"] == ["h0"]
        assert data["per_task"]["throughput_sla"]["prompt_fingerprint"] == "h0"
