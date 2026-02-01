"""
Evidence bundle verification: PASS on untouched bundle; FAIL on tampered file, tampered trace, or missing file.
"""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.export.receipts import (
    build_receipts_from_log,
    load_episode_log,
    write_evidence_bundle,
)
from labtrust_gym.export.verify import verify_bundle


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _tiny_episode_log(tmp_path: Path) -> Path:
    """Write a minimal episode log (JSONL) and return path."""
    entries = [
        {
            "t_s": 100,
            "agent_id": "A",
            "action_type": "CREATE_ACCESSION",
            "args": {"specimen_id": "S1"},
            "status": "ACCEPTED",
            "hashchain": {"head_hash": "h0", "length": 1, "last_event_hash": "e0"},
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
    log_path = tmp_path / "ep.jsonl"
    with log_path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, sort_keys=True) + "\n")
    return log_path


def test_verify_bundle_pass_untouched(tmp_path: Path) -> None:
    """Generate tiny bundle from episode log; verify PASS on untouched bundle."""
    root = _repo_root()
    log_path = _tiny_episode_log(tmp_path)
    entries = load_episode_log(log_path)
    receipts = build_receipts_from_log(entries)
    out_dir = tmp_path / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(
        out_dir,
        receipts,
        entries,
        policy_fingerprint="fp_test",
        partner_id=None,
    )
    passed, report, errors = verify_bundle(
        bundle_dir,
        policy_root=root,
        allow_extra_files=False,
    )
    assert passed, f"expected PASS: {report}\n{errors}"
    assert "PASS" in report
    assert len(errors) == 0


def test_verify_bundle_fail_tampered_file(tmp_path: Path) -> None:
    """Tamper with one file (change receipt content) -> verify FAIL (hash mismatch)."""
    root = _repo_root()
    log_path = _tiny_episode_log(tmp_path)
    entries = load_episode_log(log_path)
    receipts = build_receipts_from_log(entries)
    out_dir = tmp_path / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(out_dir, receipts, entries)
    # Tamper: change one receipt file
    receipt_files = list(bundle_dir.glob("receipt_*.v0.1.json"))
    assert receipt_files
    tampered = receipt_files[0]
    data = json.loads(tampered.read_text(encoding="utf-8"))
    data["decision"] = "BLOCKED"
    tampered.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
    passed, report, errors = verify_bundle(
        bundle_dir,
        policy_root=root,
        allow_extra_files=False,
    )
    assert not passed
    assert any("hash mismatch" in e for e in errors) or any(
        "manifest" in e.lower() for e in errors
    )


def test_verify_bundle_fail_tampered_invariant_trace(tmp_path: Path) -> None:
    """Tamper invariant_eval_trace (add violation not in log) -> verify FAIL."""
    root = _repo_root()
    log_path = _tiny_episode_log(tmp_path)
    entries = load_episode_log(log_path)
    receipts = build_receipts_from_log(entries)
    out_dir = tmp_path / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(out_dir, receipts, entries)
    trace_path = bundle_dir / "invariant_eval_trace.jsonl"
    # Add fake violation for step 0 not in log
    if trace_path.exists():
        lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    else:
        lines = []
    fake_row = json.dumps(
        {
            "step_index": 0,
            "t_s": 100,
            "violations": [
                {"invariant_id": "FAKE_INV", "status": "VIOLATION", "reason_code": "FAKE"}
            ],
        },
        sort_keys=True,
    )
    trace_path.write_text("\n".join(lines + [fake_row]) + "\n", encoding="utf-8")
    # Recompute manifest so trace file hash matches (else we fail on manifest first)
    import hashlib
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    new_files = []
    for f in manifest["files"]:
        if f["path"] == "invariant_eval_trace.jsonl":
            new_files.append({
                "path": f["path"],
                "sha256": hashlib.sha256(
                    trace_path.read_bytes()
                ).hexdigest(),
            })
        else:
            new_files.append(f)
    manifest["files"] = new_files
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    passed, report, errors = verify_bundle(
        bundle_dir,
        policy_root=root,
        allow_extra_files=False,
    )
    assert not passed
    assert any("invariant_eval_trace" in e for e in errors) or any(
        "violation" in e.lower() for e in errors
    )


def test_verify_bundle_fail_missing_file(tmp_path: Path) -> None:
    """Remove file referenced in manifest -> verify FAIL (missing file)."""
    root = _repo_root()
    log_path = _tiny_episode_log(tmp_path)
    entries = load_episode_log(log_path)
    receipts = build_receipts_from_log(entries)
    out_dir = tmp_path / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(out_dir, receipts, entries)
    receipt_files = list(bundle_dir.glob("receipt_*.v0.1.json"))
    assert receipt_files
    receipt_files[0].unlink()
    passed, report, errors = verify_bundle(
        bundle_dir,
        policy_root=root,
        allow_extra_files=False,
    )
    assert not passed
    assert any("missing" in e.lower() for e in errors)


def test_verify_bundle_fail_no_manifest(tmp_path: Path) -> None:
    """Directory without manifest.json -> FAIL."""
    root = _repo_root()
    (tmp_path / "foo.txt").write_text("x", encoding="utf-8")
    passed, report, errors = verify_bundle(
        tmp_path,
        policy_root=root,
        allow_extra_files=False,
    )
    assert not passed
    assert any("manifest" in e.lower() for e in errors)


def test_verify_bundle_allow_extra_files(tmp_path: Path) -> None:
    """With allow_extra_files, extra file (e.g. fhir_bundle.json) does not cause FAIL."""
    root = _repo_root()
    log_path = _tiny_episode_log(tmp_path)
    entries = load_episode_log(log_path)
    receipts = build_receipts_from_log(entries)
    out_dir = tmp_path / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(out_dir, receipts, entries)
    (bundle_dir / "fhir_bundle.json").write_text(
        json.dumps(
            {"resourceType": "Bundle", "type": "collection", "entry": []},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    passed, report, errors = verify_bundle(
        bundle_dir,
        policy_root=root,
        allow_extra_files=True,
    )
    assert passed, (
        f"expected PASS with allow_extra_files: {report}\n{errors}"
    )
