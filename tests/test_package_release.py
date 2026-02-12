"""
Package-release: determinism test (same seed_base => identical MANIFEST hashes).
Paper profile: smoke test with LABTRUST_PAPER_SMOKE=1 and layout/artifact checks.
CLI integration: labtrust package-release --profile paper_v0.1 works end-to-end.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.studies.package_release import (
    _deterministic_timestamp,
    run_package_release,
)


def test_deterministic_timestamp() -> None:
    """_deterministic_timestamp(seed_base) is deterministic and UTC epoch + seed_base seconds."""
    assert _deterministic_timestamp(0) == "1970-01-01T00:00:00Z"
    assert _deterministic_timestamp(100) == "1970-01-01T00:01:40Z"
    assert _deterministic_timestamp(3661) == "1970-01-01T01:01:01Z"
    # Same input => same output
    assert _deterministic_timestamp(42) == _deterministic_timestamp(42)


@pytest.mark.slow
def test_package_release_determinism() -> None:
    """Run package-release twice with same seed_base; MANIFEST paths must match; non-plot file hashes must be identical (plots may vary by matplotlib backend)."""
    seed_base = 4242
    with tempfile.TemporaryDirectory() as tmp:
        out1 = Path(tmp) / "release1"
        out2 = Path(tmp) / "release2"
        run_package_release(
            profile="minimal",
            out_dir=out1,
            seed_base=seed_base,
            include_repro_dir=False,
        )
        run_package_release(
            profile="minimal",
            out_dir=out2,
            seed_base=seed_base,
            include_repro_dir=False,
        )
        m1_path = out1 / "MANIFEST.v0.1.json"
        m2_path = out2 / "MANIFEST.v0.1.json"
        assert m1_path.exists()
        assert m2_path.exists()
        manifest1 = json.loads(m1_path.read_text(encoding="utf-8"))
        manifest2 = json.loads(m2_path.read_text(encoding="utf-8"))
        files1 = {f["path"]: f["sha256"] for f in (manifest1.get("files") or [])}
        files2 = {f["path"]: f["sha256"] for f in (manifest2.get("files") or [])}
        assert set(files1.keys()) == set(files2.keys()), "MANIFEST path list must be identical"
        skip_paths = {"plots/", "results.json"}
        for path in files1:
            if any(path.startswith(p) or path == p for p in skip_paths):
                continue
            assert files1[path] == files2[path], f"MANIFEST hash for {path} must be identical for same seed_base"


@pytest.mark.slow
def test_package_release_produces_expected_files() -> None:
    """package-release produces MANIFEST, BENCHMARK_CARD, metadata, results.json, plots/, tables/, receipts/, fhir/."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "release"
        run_package_release(
            profile="minimal",
            out_dir=out,
            seed_base=100,
            include_repro_dir=False,
        )
        assert (out / "MANIFEST.v0.1.json").exists()
        assert (out / "BENCHMARK_CARD.md").exists()
        assert (out / "metadata.json").exists()
        assert (out / "results.json").exists()
        assert out / "plots"
        assert out / "tables"
        assert out / "receipts"
        assert out / "fhir"
        meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
        assert "seed_base" in meta
        assert "profile" in meta
        assert meta["seed_base"] == 100
        assert meta["profile"] == "minimal"


@pytest.mark.slow
def test_package_release_paper_v01_smoke() -> None:
    """paper_v0.1 profile with LABTRUST_PAPER_SMOKE=1 produces complete self-contained artifact dir."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "paper_release"
        prev = os.environ.get("LABTRUST_PAPER_SMOKE")
        try:
            os.environ["LABTRUST_PAPER_SMOKE"] = "1"
            run_package_release(
                profile="paper_v0.1",
                out_dir=out,
                seed_base=100,
            )
        finally:
            if prev is None:
                os.environ.pop("LABTRUST_PAPER_SMOKE", None)
            else:
                os.environ["LABTRUST_PAPER_SMOKE"] = prev

        assert (out / "RELEASE_NOTES.md").exists()
        assert (out / "metadata.json").exists()
        assert (out / "BENCHMARK_CARD.md").exists()
        assert (out / "MANIFEST.v0.1.json").exists()
        assert (out / "FIGURES").is_dir()
        assert (out / "TABLES").is_dir()
        assert (out / "TABLES" / "summary.csv").exists()
        assert (out / "TABLES" / "summary.md").exists()
        assert (out / "TABLES" / "paper_table.md").exists()
        assert (out / "_baselines").is_dir()
        assert (out / "_baselines" / "results").is_dir()
        assert (out / "_study").is_dir()
        assert (out / "receipts").is_dir()
        assert (out / "_repr").is_dir()
        assert (out / "COORDINATION_CARD.md").exists()
        assert (out / "_coordination_policy").is_dir()
        assert (out / "_coordination_policy" / "manifest.json").exists()
        assert (out / "SECURITY" / "deps_inventory_runtime.json").exists()
        assert (out / "TRANSPARENCY_LOG" / "log.json").exists()
        assert (out / "TRANSPARENCY_LOG" / "root.txt").exists()
        assert (out / "TRANSPARENCY_LOG" / "proofs").is_dir()
        assert (out / "SAFETY_CASE" / "safety_case.json").exists()
        assert (out / "SAFETY_CASE" / "safety_case.md").exists()

        meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
        assert meta["profile"] == "paper_v0.1"
        assert meta["seed_base"] == 100
        assert "timestamp" in meta
        # Determinism: timestamp must match _deterministic_timestamp(seed_base)
        expected_ts = _deterministic_timestamp(100)
        assert meta["timestamp"] == expected_ts, (
            f"paper profile must use deterministic timestamp for seed_base=100: "
            f"expected {expected_ts!r}, got {meta['timestamp']!r}"
        )


@pytest.mark.slow
def test_package_release_paper_v01_cli() -> None:
    """CLI: labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir> works offline."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "paper_cli"
        prev = os.environ.get("LABTRUST_PAPER_SMOKE")
        try:
            os.environ["LABTRUST_PAPER_SMOKE"] = "1"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "labtrust_gym.cli.main",
                    "package-release",
                    "--profile",
                    "paper_v0.1",
                    "--seed-base",
                    "100",
                    "--out",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            assert proc.returncode == 0, f"CLI must exit 0: stderr={proc.stderr!r} stdout={proc.stdout!r}"
        finally:
            if prev is None:
                os.environ.pop("LABTRUST_PAPER_SMOKE", None)
            else:
                os.environ["LABTRUST_PAPER_SMOKE"] = prev

        assert (out / "RELEASE_NOTES.md").exists()
        assert (out / "metadata.json").exists()
        assert (out / "COORDINATION_CARD.md").exists()
        assert (out / "_coordination_policy" / "manifest.json").exists()
        assert (out / "TABLES" / "summary.csv").exists()
        assert (out / "TABLES" / "paper_table.md").exists()
        meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
        assert meta["profile"] == "paper_v0.1"
        assert meta["seed_base"] == 100
