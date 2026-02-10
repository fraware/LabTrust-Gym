"""
Official Benchmark Pack v0.1: smoke test.

Runs with LABTRUST_OFFICIAL_PACK_SMOKE=1 or LABTRUST_PAPER_SMOKE=1.
Asserts required folders exist and verify-bundle passes on a minimal bundle.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.official_pack import (
    _all_pack_tasks,
    load_benchmark_pack,
    run_official_pack,
)
from labtrust_gym.config import get_repo_root


def test_load_benchmark_pack() -> None:
    """Pack policy loads; has tasks, scale_configs, baselines, required_reports."""
    root = get_repo_root()
    pack, pack_version, pack_policy_path = load_benchmark_pack(root)
    assert pack_version == "0.1"
    assert pack.get("version") == "0.1"
    tasks = _all_pack_tasks(pack)
    assert "throughput_sla" in tasks
    assert "coord_risk" in tasks
    scale_configs = pack.get("scale_configs") or {}
    assert "S" in scale_configs or not scale_configs
    assert "security" in (pack.get("required_reports") or [])
    assert "safety_case" in (pack.get("required_reports") or [])


def test_load_benchmark_pack_prefer_v02_returns_v02_when_present() -> None:
    """When prefer_v02=True and v0.2 policy exists, load_benchmark_pack returns v0.2 pack."""
    root = get_repo_root()
    v02_path = root / "policy" / "official" / "benchmark_pack.v0.2.yaml"
    if not v02_path.exists():
        pytest.skip("benchmark_pack.v0.2.yaml not present")
    pack, pack_version, pack_policy_path = load_benchmark_pack(root, prefer_v02=True)
    assert pack_version == "0.2"
    assert pack.get("version") == "0.2"
    assert "benchmark_pack.v0.2" in pack_policy_path
    assert "live_coordination_evaluation_protocol" in pack


def test_official_pack_smoke_required_folders() -> None:
    """Run official pack with smoke; assert required folders and files exist."""
    root = get_repo_root()
    prev = os.environ.get("LABTRUST_OFFICIAL_PACK_SMOKE"), os.environ.get("LABTRUST_PAPER_SMOKE")
    try:
        os.environ["LABTRUST_OFFICIAL_PACK_SMOKE"] = "1"
        if "LABTRUST_PAPER_SMOKE" in os.environ:
            del os.environ["LABTRUST_PAPER_SMOKE"]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pack"
            run_official_pack(
                out_dir=out,
                repo_root=root,
                seed_base=100,
                smoke=True,
                full_security=False,
            )
            assert (out / "baselines" / "results").is_dir()
            assert (out / "SECURITY").is_dir()
            assert (out / "SAFETY_CASE").is_dir()
            assert (out / "TRANSPARENCY_LOG").is_dir()
            assert (out / "pack_manifest.json").exists()
            assert (out / "PACK_SUMMARY.md").exists()
            manifest = __import__("json").loads((out / "pack_manifest.json").read_text(encoding="utf-8"))
            assert manifest.get("version") == "0.1"
            assert "tasks" in manifest
            assert "seed_base" in manifest
            assert manifest.get("pipeline_mode") == "deterministic"
    finally:
        if prev[0] is not None:
            os.environ["LABTRUST_OFFICIAL_PACK_SMOKE"] = prev[0]
        elif "LABTRUST_OFFICIAL_PACK_SMOKE" in os.environ:
            os.environ.pop("LABTRUST_OFFICIAL_PACK_SMOKE")
        if prev[1] is not None:
            os.environ["LABTRUST_PAPER_SMOKE"] = prev[1]


def test_official_pack_llm_live_writes_transparency_artifacts() -> None:
    """With pipeline_mode=llm_live, pack writes TRANSPARENCY_LOG/llm_live.json and live_evaluation_metadata.json."""
    root = get_repo_root()
    if os.environ.get("LABTRUST_OFFICIAL_PACK_SMOKE") != "1" and os.environ.get("LABTRUST_PAPER_SMOKE") != "1":
        pytest.skip("Set LABTRUST_OFFICIAL_PACK_SMOKE=1 or LABTRUST_PAPER_SMOKE=1 to run")
    prev = os.environ.get("LABTRUST_OFFICIAL_PACK_SMOKE"), os.environ.get("LABTRUST_PAPER_SMOKE")
    try:
        os.environ["LABTRUST_OFFICIAL_PACK_SMOKE"] = "1"
        if "LABTRUST_PAPER_SMOKE" in os.environ:
            del os.environ["LABTRUST_PAPER_SMOKE"]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pack_llm_live"
            run_official_pack(
                out_dir=out,
                repo_root=root,
                seed_base=100,
                smoke=True,
                full_security=False,
                pipeline_mode="llm_live",
                allow_network=False,
            )
            assert (out / "TRANSPARENCY_LOG" / "llm_live.json").exists()
            assert (out / "live_evaluation_metadata.json").exists()
            manifest = __import__("json").loads((out / "pack_manifest.json").read_text(encoding="utf-8"))
            assert manifest.get("pipeline_mode") == "llm_live"
            assert manifest.get("version") == "0.2"
            meta = __import__("json").loads((out / "live_evaluation_metadata.json").read_text(encoding="utf-8"))
            assert "allow_network" in meta
            assert meta["allow_network"] is False
    finally:
        if prev[0] is not None:
            os.environ["LABTRUST_OFFICIAL_PACK_SMOKE"] = prev[0]
        elif "LABTRUST_OFFICIAL_PACK_SMOKE" in os.environ:
            os.environ.pop("LABTRUST_OFFICIAL_PACK_SMOKE")
        if prev[1] is not None:
            os.environ["LABTRUST_PAPER_SMOKE"] = prev[1]


def test_verify_bundle_runs() -> None:
    """verify-bundle runs on fixture evidence bundle and returns (passed, report, errors)."""
    from labtrust_gym.export.verify import verify_bundle

    root = get_repo_root()
    bundle_path = root / "ui_fixtures" / "evidence_bundle" / "EvidenceBundle.v0.1"
    if not bundle_path.is_dir():
        pytest.skip("ui_fixtures/evidence_bundle/EvidenceBundle.v0.1 not found")
    passed, report, errors = verify_bundle(bundle_path, policy_root=root, allow_extra_files=True)
    assert isinstance(passed, bool)
    assert isinstance(report, str)
    assert isinstance(errors, list)


def test_verify_bundle_passes_on_minimal_bundle(tmp_path: Path) -> None:
    """Verify-bundle passes on a minimal evidence bundle (full chain: export then verify)."""
    import json

    from labtrust_gym.export.receipts import (
        build_receipts_from_log,
        load_episode_log,
        write_evidence_bundle,
    )
    from labtrust_gym.export.verify import verify_bundle

    root = get_repo_root()
    log_path = tmp_path / "ep.jsonl"
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
    with log_path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, sort_keys=True) + "\n")
    loaded = load_episode_log(log_path)
    receipts = build_receipts_from_log(loaded)
    out_dir = tmp_path / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(
        out_dir,
        receipts,
        loaded,
        policy_fingerprint="fp_test",
        partner_id=None,
    )
    passed, report, errors = verify_bundle(
        bundle_dir,
        policy_root=root,
        allow_extra_files=False,
    )
    assert passed, f"verify_bundle must pass on minimal bundle: {report}\n{errors}"
    assert "PASS" in report
    assert len(errors) == 0
