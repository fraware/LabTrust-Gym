"""
LTG-PR6: independent offline reconstruction / verify from release artifacts.
No live LLM; prove EvidenceBundle + RELEASE_MANIFEST carry reconstruction fields
and verify-bundle recomputes PR2 digests.
"""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.export.receipts import (
    build_receipts_from_log,
    write_evidence_bundle,
)
from labtrust_gym.export.reconstruction import (
    RECONSTRUCTION_KEYS,
    aggregate_release_reconstruction,
    build_pack_reconstruction,
    build_reconstruction_block,
    compute_environment_digest,
    extract_run_provenance,
)
from labtrust_gym.export.verify import (
    EVIDENCE_BUNDLE_DIRNAME,
    RELEASE_MANIFEST_FILENAME,
    build_release_manifest,
    verify_bundle,
)
from labtrust_gym.orchestrator.replay import (
    canonical_episode_log_digest,
    evidence_digest,
)
from labtrust_gym.policy.loader import load_json, validate_against_schema


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _tiny_entries() -> list[dict]:
    return [
        {
            "t_s": 100,
            "agent_id": "A",
            "action_type": "CREATE_ACCESSION",
            "args": {"specimen_id": "S1"},
            "status": "ACCEPTED",
            "hashchain": {"head_hash": "h0", "length": 1, "last_event_hash": "e0"},
            "seed": 42,
            "scenario_id": "throughput_sla",
            "agent_baseline_id": "scripted_ops_v1",
        },
        {
            "t_s": 200,
            "agent_id": "A",
            "action_type": "ACCEPT_SPECIMEN",
            "args": {"specimen_id": "S1"},
            "status": "ACCEPTED",
            "hashchain": {"head_hash": "h1", "length": 2, "last_event_hash": "e1"},
        },
    ]


def test_reconstruction_block_has_required_keys() -> None:
    entries = _tiny_entries()
    block = build_reconstruction_block(
        entries=entries,
        policy_digest="fp_abc",
        agent_identity="scripted_ops_v1",
        seed=42,
        scenario_ids=["throughput_sla"],
    )
    for key in RECONSTRUCTION_KEYS:
        assert key in block, f"missing {key}"
    assert block["policy_digest"] == "fp_abc"
    assert block["environment_digest"] == compute_environment_digest(policy_digest="fp_abc")
    assert block["episode_log_digest"] == canonical_episode_log_digest(entries)
    assert block["evidence_digest"] == evidence_digest(entries)
    assert block["agent_identity"] == "scripted_ops_v1"
    assert block["seed"] == 42
    assert block["scenario_ids"] == ["throughput_sla"]


def test_evidence_bundle_writes_reconstruction_and_verify_passes(tmp_path: Path) -> None:
    root = _repo_root()
    entries = _tiny_entries()
    receipts = build_receipts_from_log(entries)
    out_dir = tmp_path / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(
        out_dir,
        receipts,
        entries,
        policy_fingerprint="fp_test",
        partner_id=None,
        agent_identity="scripted_ops_v1",
        seed=42,
        scenario_ids=["throughput_sla"],
    )
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "reconstruction" in manifest
    recon = manifest["reconstruction"]
    for key in (
        "policy_digest",
        "environment_digest",
        "agent_identity",
        "seed",
        "scenario_ids",
        "episode_log_digest",
        "evidence_digest",
        "risk_register_refs",
        "verification_results",
        "missing_evidence",
    ):
        assert key in recon
    assert recon["policy_digest"] == manifest["policy_fingerprint"]
    assert recon["agent_identity"] == "scripted_ops_v1"
    assert recon["seed"] == 42
    assert recon["scenario_ids"] == ["throughput_sla"]
    assert manifest.get("environment_digest") == recon["environment_digest"]
    assert manifest.get("episode_log_digest") == recon["episode_log_digest"]

    schema = load_json(root / "policy" / "schemas" / "evidence_bundle_manifest.v0.1.schema.json")
    validate_against_schema(manifest, schema, root / "policy" / "schemas" / "evidence_bundle_manifest.v0.1.schema.json")

    passed, report, errors = verify_bundle(bundle_dir, policy_root=root, allow_extra_files=False)
    assert passed, f"expected PASS: {report}\n{errors}"


def test_tampered_episode_log_digest_fails_verify(tmp_path: Path) -> None:
    root = _repo_root()
    entries = _tiny_entries()
    receipts = build_receipts_from_log(entries)
    out_dir = tmp_path / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(
        out_dir,
        receipts,
        entries,
        policy_fingerprint="fp_test",
        agent_identity="scripted_ops_v1",
        seed=42,
        scenario_ids=["throughput_sla"],
    )
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Tamper reconstruction digest without changing files[] hashes of episode log
    # (files[] still match on-disk content; digest field is wrong)
    manifest["reconstruction"]["episode_log_digest"] = "0" * 64
    manifest["episode_log_digest"] = "0" * 64
    from labtrust_gym.util.json_utils import canonical_json

    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    passed, _report, errors = verify_bundle(bundle_dir, policy_root=root, allow_extra_files=False)
    assert not passed
    assert any("episode_log_digest" in e for e in errors)


def test_release_manifest_aggregates_reconstruction(tmp_path: Path) -> None:
    root = _repo_root()
    entries = _tiny_entries()
    receipts = build_receipts_from_log(entries)
    out_dir = tmp_path / "bundle_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(
        out_dir,
        receipts,
        entries,
        policy_fingerprint="fp_test",
        agent_identity="scripted_ops_v1",
        seed=42,
        scenario_ids=["throughput_sla"],
    )
    release_dir = tmp_path / "release"
    dest = release_dir / "receipts" / "throughput_sla" / EVIDENCE_BUNDLE_DIRNAME
    dest.mkdir(parents=True, exist_ok=True)
    for f in bundle_dir.iterdir():
        if f.is_file():
            (dest / f.name).write_bytes(f.read_bytes())
    (release_dir / "MANIFEST.v0.1.json").write_text('{"version":"0.1","files":[]}', encoding="utf-8")
    # Missing-evidence declaration via risk register
    risk = {
        "version": "0.1",
        "evidence": [
            {
                "risk_id": "R-TEST",
                "status": "missing",
                "expected_sources": ["SECURITY/attack_results.json"],
            }
        ],
    }
    (release_dir / "RISK_REGISTER_BUNDLE.v0.1.json").write_text(
        json.dumps(risk, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    manifest_path = build_release_manifest(release_dir, policy_root=root)
    assert manifest_path.name == RELEASE_MANIFEST_FILENAME
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "reconstruction" in data
    recon = data["reconstruction"]
    assert recon.get("environment_digest") or recon.get("environment_digests")
    assert "scripted_ops_v1" in (recon.get("agent_identities") or []) or recon.get("agent_identity") == "scripted_ops_v1"
    assert 42 in (recon.get("seeds") or []) or recon.get("seed") == 42
    assert "throughput_sla" in (recon.get("scenario_ids") or [])
    assert recon.get("episode_log_digests")
    assert "RISK_REGISTER_BUNDLE.v0.1.json" in (recon.get("risk_register_refs") or [])
    assert recon.get("verification_results", {}).get("status") == "offline_verifiable"
    assert any(m.get("risk_id") == "R-TEST" for m in (recon.get("missing_evidence") or []))

    schema = load_json(root / "policy" / "schemas" / "release_manifest.v0.1.schema.json")
    validate_against_schema(data, schema, root / "policy" / "schemas" / "release_manifest.v0.1.schema.json")

    # Risk register schema may fail full verify_release; still check bundles + RELEASE_MANIFEST hashes
    from labtrust_gym.export.verify import verify_release

    all_passed, results, release_errors = verify_release(release_dir, policy_root=root)
    assert results and results[0][1] is True
    # Minimal risk fixture is intentionally incomplete for schema; filter those errors
    hash_errors = [e for e in release_errors if "RELEASE_MANIFEST" in e or "hash mismatch" in e]
    assert not hash_errors, hash_errors
    # Bundle verify portion of release must pass
    assert all(r[1] for r in results)


def test_pack_reconstruction_schema() -> None:
    root = _repo_root()
    recon = build_pack_reconstruction(
        seed_base=100,
        tasks=["throughput_sla", "qc_cascade"],
        baselines={"throughput_sla": "scripted_ops_v1", "qc_cascade": "adversary_v1"},
        policy_digest="pack_fp",
    )
    pack = {
        "version": "0.1",
        "seed_base": 100,
        "tasks": ["throughput_sla", "qc_cascade"],
        "reconstruction": recon,
    }
    schema = load_json(root / "policy" / "schemas" / "pack_manifest.v0.1.schema.json")
    validate_against_schema(pack, schema, root / "policy" / "schemas" / "pack_manifest.v0.1.schema.json")
    assert recon["seed"] == 100
    assert set(recon["scenario_ids"]) == {"throughput_sla", "qc_cascade"}
    assert "scripted_ops_v1" in recon["agent_identities"]
    assert recon["environment_digest"]


def test_extract_run_provenance_from_results() -> None:
    meta = {
        "task": "throughput_sla",
        "base_seed": 7,
        "agent_baseline_id": "ppo_v1",
        "seeds": [7, 8],
    }
    prov = extract_run_provenance(meta)
    assert prov["agent_identity"] == "ppo_v1"
    assert prov["seed"] == 7
    assert prov["scenario_ids"] == ["throughput_sla"]


def test_aggregate_release_reconstruction_merges_pack() -> None:
    bundled = [
        build_reconstruction_block(
            entries=_tiny_entries(),
            policy_digest="fp1",
            agent_identity="scripted_ops_v1",
            seed=1,
            scenario_ids=["throughput_sla"],
        )
    ]
    pack = build_pack_reconstruction(
        seed_base=100,
        tasks=["qc_cascade"],
        baselines={"qc_cascade": "adversary_v1"},
        policy_digest="fp1",
    )
    agg = aggregate_release_reconstruction(
        bundle_reconstructions=bundled,
        risk_register_path="RISK_REGISTER_BUNDLE.v0.1.json",
        missing_evidence=[{"risk_id": "R1", "status": "missing", "expected_sources": []}],
        pack_reconstruction=pack,
    )
    assert "throughput_sla" in agg["scenario_ids"]
    assert "qc_cascade" in agg["scenario_ids"]
    assert "adversary_v1" in agg["agent_identities"]
    assert agg["risk_register_refs"] == ["RISK_REGISTER_BUNDLE.v0.1.json"]
    assert agg["missing_evidence"][0]["risk_id"] == "R1"


def test_export_receipts_reads_results_json(tmp_path: Path) -> None:
    from labtrust_gym.export.receipts import export_receipts

    root = _repo_root()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    entries = _tiny_entries()
    # Strip identity from log so results.json is the source
    for e in entries:
        e.pop("agent_baseline_id", None)
        e.pop("scenario_id", None)
        e.pop("seed", None)
    log_path = run_dir / "episode.jsonl"
    with log_path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, sort_keys=True) + "\n")
    (run_dir / "results.json").write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "task": "throughput_sla",
                "seeds": [99],
                "base_seed": 99,
                "agent_baseline_id": "scripted_ops_v1",
                "episodes": [{"seed": 99, "metrics": {}}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    bundle = export_receipts(log_path, out, policy_fingerprint="fp_x")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    recon = manifest["reconstruction"]
    assert recon["agent_identity"] == "scripted_ops_v1"
    assert recon["seed"] == 99
    assert "throughput_sla" in recon["scenario_ids"]
    passed, _, errors = verify_bundle(bundle, policy_root=root)
    assert passed, errors


def test_legacy_fixture_without_reconstruction_still_verifies() -> None:
    """Committed release fixture manifests may lack reconstruction; verify must not require it."""
    root = _repo_root()
    fixture = root / "tests" / "fixtures" / "release_fixture_minimal"
    if not fixture.is_dir():
        return
    from labtrust_gym.export.verify import verify_release

    all_passed, results, release_errors = verify_release(
        fixture,
        policy_root=root,
        strict_fingerprints=True,
    )
    assert results, "expected bundles in release fixture"
    # Reconstruction absence must not be the failure mode
    for _path, _ok, _report, errors in results:
        assert not any("reconstruction" in e and "missing" in e.lower() for e in errors)
